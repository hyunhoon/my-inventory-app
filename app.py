import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# 페이지 설정
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")

st.title("📊 의약품 통합 분석 시스템")
st.markdown("---")

ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

def load_data(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)

if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    
    # 데이터 로드 및 정제 로직은 기존과 동일
    df_orders = load_data(ORDER_FILE)
    df_inventory = load_data(INVENTORY_FILE)
    
    # 데이터 정리
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
    df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
    df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
    df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')

    # 탭 구성 (탭 5만 수정)
    t1, t2, t3, t4, t5 = st.tabs(["🏢 매출처별 출고", "⚠️ 주문부족 알림", "🚨 유효기간 경고", "📦 장기 미출고", "📋 전체 현재 재고"])
    
    # --- [탭 5] 전체 현재 재고 (체크박스 선택 방식) ---
    with t5:
        st.header("▶️ 창고 전체 현재 재고 현황")
        
        # 데이터프레임 구성
        df_f = df_inventory[['제품명', '재고수량', '유효기간']].drop_duplicates().sort_values('제품명').copy()
        
        # 체크박스 컬럼 추가 (맨 앞에 생성)
        df_f.insert(0, "선택", False)
        
        st.caption("💡 아래 리스트에서 확인하고 싶은 의약품의 **네모 박스(체크박스)를 클릭**하세요.")
        
        # 체크박스 에디터 (st.data_editor 사용)
        edited_df = st.data_editor(
            df_f,
            column_config={
                "선택": st.column_config.CheckboxColumn(required=True),
                "재고수량": st.column_config.NumberColumn(format="%d"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # 체크된 행 찾기
        selected_rows = edited_df[edited_df["선택"] == True]
        
        st.markdown("---")
        st.subheader("📊 선택한 의약품의 거래처별 출고 이력 상세 조회")
        
        if not selected_rows.empty:
            # 체크박스가 여러 개 눌릴 경우 첫 번째 항목을 우선 조회
            target_product = selected_rows.iloc[0]['제품명']
            
            st.info(f"✅ 현재 선택된 의약품: **{target_product}**")
            
            # 출고 이력 필터링
            df_p_ord = df_orders[df_orders['제품명'] == target_product].sort_values('출고일자', ascending=False)
            
            if not df_p_ord.empty:
                df_disp = df_p_ord[['출고일자', '매출처', '수량']].copy()
                df_disp['출고일자'] = df_disp['출고일자'].dt.strftime('%Y-%m-%d')
                st.dataframe(df_disp, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ 해당 의약품의 출고 기록이 없습니다.")
        else:
            st.info("💡 위 리스트에서 제품명 앞의 **네모 박스를 체크**하면 상세 이력이 여기에 나타납니다.")

else:
    st.error("데이터 파일을 찾을 수 없습니다.")