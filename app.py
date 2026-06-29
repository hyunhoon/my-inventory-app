import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# 페이지 설정
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")

st.title("📊 의약품 통합 분석 시스템")
st.write("데이터를 자동으로 불러와 분석하는 화면입니다.")
st.markdown("---")

ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

def load_data(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)

if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    
    try:
        df_orders = load_data(ORDER_FILE)
        df_inventory = load_data(INVENTORY_FILE)
        
        # 공백 및 문자열 정리
        if '제품명' in df_orders.columns:
            df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
        if '제품명' in df_inventory.columns:
            df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
        if '매출처' in df_orders.columns:
            df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str).str.strip()
            
        # 합계 데이터 및 "금융비용할인" 항목 전면 제외 처리
        k_word = '합계|합 계|\\[합.*\\]|금융비용할인'
        df_orders = df_orders[(df_orders['제품명'] != '') & (~df_orders['제품명'].str.contains(k_word, na=False))]
        df_inventory = df_inventory[(df_inventory['제품명'] != '') & (~df_inventory['제품명'].str.contains(k_word, na=False))]
        
        if '매출처' in df_orders.columns:
            df_orders = df_orders[~df_orders['매출처'].str.contains('금융비용할인', na=False)]
        
        # 숫자 데이터 변환
        if '수량' in df_orders.columns:
            df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
        if '재고수량' in df_inventory.columns:
            df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
            
        # 날짜형 변환
        if '출고일자' in df_orders.columns:
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')

        # 유효기간 날짜 파싱
        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))
        else:
            df_inventory['유효기간_표시'] = "기록없음"

        data_ready = True
    except Exception as e:
        st.error(f"❌ 데이터 정제 중 오류 발생: {e}")
        data_ready = False

    if data_ready:
        t1, t2, t3, t4, t5 = st.tabs(["🏢 매출처별 출고", "⚠️ 주문시기/재고부족", "🚨 유효기간 임박", "📦 장기 미출고", "📋 전체 현재 재고"])
        
        with t1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
            df_cust = pd.DataFrame(u_cust, columns=['매출처'])
            c_search = st.text_input("🔍 매출처 검색:", "", key="c_search_t1")
            if c_search: df_cust = df_cust[df_cust['매출처'].str.contains(c_search, case=False, na=False)]
            df_cust.insert(0, "선택", False)
            edited_df1 = st.data_editor(df_cust, column_config={"선택": st.column_config.CheckboxColumn(required=True, width=50)}, use_container_width=True, hide_index=True)
            sel1 = edited_df1[edited_df1["선택"] == True]
            if not sel1.empty:
                s_cust = sel1.iloc[0]['매출처']
                st.markdown(f"### 📅 [{s_cust}] 상세 내역")
                df_c = df_orders[df_orders['매출처'] == s_cust].sort_values('출고일자', ascending=False)
                st.dataframe(df_c[['출고일자', '제품명', '수량']], use_container_width=True, hide_index=True)

        with t2:
            st.header("▶️ 주문 시기 및 재고 부족 위험")
            if not df_orders.empty and '출고일자' in df_orders.columns:
                df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
                df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
                df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
                cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
                cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)].copy()
                cyc['예상일'] = cyc.apply(lambda r: r['r_il'] + timedelta(days=int(r['p_ju'])), axis=1)
                cyc['남은일'] = (cyc['예상일'] - current_date).dt.days
                alert = cyc[(cyc['남은일'] <= 7) & (~cyc['제품명'].str.contains('하모닐란|엔커버', na=False))].copy()
                for idx, row in alert.iterrows():
                    stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                    if stk < row['p_am']:
                        st.warning(f"**[{row['매출처']}]** {row['제품명']} • 예상일: {row['예상일'].strftime('%Y-%m-%d')} ({row['남은일']}일 남음) • 재고: {stk:.0f}개")

        with t3:
            st.header("▶️ 유효기간 365일 미만")
            lim_365 = current_date + timedelta(days=365)
            s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & (df_inventory['유효기간_날짜'] <= lim_365) & (df_inventory['재고수량'] > 0)]
            for idx, row in s_exp.sort_values(by='유효기간_날짜').iterrows():
                rem_d = (row['유효기간_날짜'] - current_date).days
                if rem_d < 180: st.error(f"💥 [초긴급] {row['제품명']} ({row['재고수량']:.0f}개) • {rem_d}일 남음")
                else: st.warning(f"⚠️ [주의] {row['제품명']} ({row['재고수량']:.0f}개) • {rem_d}일 남음")

        with t4:
            st.header("▶️ 90일 이상 장기 미출고 의약품")
            df_l = df_orders.groupby('제품명')['출고일자'].max().reset_index()
            df_l.columns = ['제품명', '최종일']
            df_chk = pd.merge(df_inventory, df_l, on='제품명', how='left')
            df_chk = df_chk[df_chk['재고수량'] > 0].copy()
            df_chk['경과일'] = (current_date - df_chk['최종일']).dt.days
            
            # 여기서 수정: 데이터프레임 전체에 대한 조건식을 사용
            filtered_df = df_chk[(df_chk['경과일'] > 90) | (df_chk['최종일'].isna())]
            for idx, row in filtered_df.iterrows():
                days_txt = f"{int(row['경과일'])}일 경과" if pd.notna(row['경과일']) else "기록없음"
                st.info(f"📦 {row['제품명']} ({row['재고수량']:.0f}개) • 경과: {days_txt}")

        with t5:
            st.header("▶️ 창고 전체 재고 현황")
            df_f = df_inventory[['제품명', '재고수량', '유효기간_표시']].copy()
            df_f.columns = ['제품명', '재고 수량', '유효기간']
            p_search = st.text_input("🔍 품목명 검색:", "", key="p_search_t5")
            if p_search: df_f = df_f[df_f['제품명'].str.contains(p_search, case=False, na=False)]
            df_f.insert(0, "선택", False)
            edited_df5 = st.data_editor(df_f, column_config={"선택": st.column_config.CheckboxColumn(required=True, width=50)}, use_container_width=True, hide_index=True)
            sel5 = edited_df5[edited_df5["선택"] == True]
            if not sel5.empty:
                target = sel5.iloc[0]['제품명']
                st.markdown(f"### 📊 [{target}] 상세 내역")
                st.dataframe(df_orders[df_orders['제품명'] == target], use_container_width=True, hide_index=True)
else:
    st.error("데이터 파일을 찾을 수 없습니다.")