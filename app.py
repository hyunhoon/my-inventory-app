import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import json # 알림 기록용
import requests # 텔레그램 전송용

# 텔레그램 설정 (이 부분만 본인의 값으로 바꾸세요)
TELEGRAM_TOKEN = "AAFrFB26q547kfnj9-xRwHnyVj1qRs0KdlI"
TELEGRAM_CHAT_ID = "5953515925"
LOG_FILE = "alert_log.json"

# --- [텔레그램 알림 기능 추가 (기존 코드와 독립적으로 작동)] ---
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.get(url, params=params)
    except: pass

def load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return []

def save_log(log):
    with open(LOG_FILE, 'w', encoding='utf-8') as f: json.dump(log, f)

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
            
        k_word = '합계|합 계|\\[합.*\\]|금융비용할인'
        df_orders = df_orders[(df_orders['제품명'] != '') & (~df_orders['제품명'].str.contains(k_word, na=False))]
        df_inventory = df_inventory[(df_inventory['제품명'] != '') & (~df_inventory['제품명'].str.contains(k_word, na=False))]
        
        if '매출처' in df_orders.columns:
            df_orders = df_orders[~df_orders['매출처'].str.contains('금융비용할인', na=False)]
        
        if '수량' in df_orders.columns:
            df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
        if '재고수량' in df_inventory.columns:
            df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
            
        if '출고일자' in df_orders.columns:
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')

        exist_p = df_inventory['제품명'].unique()
        all_p = df_orders['제품명'].unique()
        miss_p = [p for p in all_p if p not in exist_p and p != '']
        
        if miss_p:
            m_df = pd.DataFrame({'제품명': miss_p, '재고수량': 0.0, '유효기간': '소진 (기록없음)'})
            df_inventory = pd.concat([df_inventory, m_df], ignore_index=True)

        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))
        else:
            df_inventory['유효기간_날짜'] = pd.NaT
            df_inventory['유효기간_표시'] = "기록없음"

        data_ready = True
    except Exception as e:
        st.error(f"❌ 데이터 정제 중 오류 발생: {e}")
        data_ready = False

    if data_ready:
        st.success(f"✅ 분석 완료! ({current_date.strftime('%Y-%m-%d')})")
        
        t1, t2, t3, t4, t5 = st.tabs([
            "🏢 매출처별 출고 리스트",
            "⚠️ 주문시기 및 재고부족 알림", 
            "🚨 유효기간 임박 경고", 
            "📦 장기 미출고 재고",
            "📋 전체 현재 재고"
        ])
        
        with t1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            if not df_orders.empty and '매출처' in df_orders.columns:
                u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
                c_search = st.text_input("🔍 매출처 검색:", "", key="c_search")
                f_cust = [c for c in u_cust if c_search.lower() in c.lower()] if c_search else u_cust
                if f_cust:
                    s_cust = st.selectbox("🏢 조회할 매출처 선택:", f_cust, key="c_select")
                    st.markdown("---")
                    st.markdown(f"### 📅 {s_cust} 상세 내역")
                    df_c_ord = df_orders[df_orders['매출처'] == s_cust].copy()
                    if not df_c_ord.empty and '출고일자' in df_c_ord.columns:
                        df_c_his = df_c_ord[['출고일자', '제품명', '수량']].copy()
                        df_c_his['출고날짜'] = df_c_his['출고일자'].dt.strftime('%Y-%m-%d').fillna("없음")
                        df_disp = df_c_his[['출고날짜', '제품명', '수량']].copy()
                        df_disp.columns = ['출고날짜', '의약품명', '출고수량 (개)']
                        df_disp = df_disp.sort_values(by='출고날짜', ascending=False)
                        st.dataframe(df_disp, use_container_width=True, hide_index=True)

        with t2:
            st.header("▶️ 주문 시기 및 재고 부족 위험")
            alert_log = load_log() # 알림 로그 로드
            if not df_orders.empty and '매출처' in df_orders.columns and '출고일자' in df_orders.columns:
                df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
                df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
                df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
                cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
                cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)].copy()
                if not cyc.empty:
                    cyc['예상일'] = cyc.apply(lambda r: r['r_il'] + timedelta(days=int(r['p_ju'])), axis=1)
                    cyc['남은일'] = (cyc['예상일'] - current_date).dt.days
                    alert = cyc[(cyc['남은일'] <= 7) & (~cyc['제품명'].str.contains('하모닐란|엔커버', na=False))].copy()
                    alert = alert[(current_date - alert['r_il']).dt.days < 60].copy()
                    p_c_vol = df_orders.groupby(['매출처', '제품명'])['수량'].sum().reset_index(name='품목별거래량')
                    alert = pd.merge(alert, p_c_vol, on=['매출처', '제품명'], how='left')
                    alert = alert.sort_values(by=['품목별거래량', '남은일'], ascending=[False, True])
                    for idx, row in alert.iterrows():
                        stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                        if stk < row['p_am']:
                            st.warning(f"**[{row['매출처']}]** {row['제품명']}\n• 예상일: {row['예상일'].strftime('%Y-%m-%d')} ({row['남은일']}일 남음)\n• 주문량: {row['p_am']:.0f}개 | 재고: {stk:.0f}개")
                            
                            # 알림 로직
                            alert_key = f"order_{row['매출처']}_{row['제품명']}"
                            if alert_key not in alert_log:
                                send_telegram(f"⚠️ [재고부족 알림]\n{row['매출처']} - {row['제품명']}\n재고: {stk:.0f}개")
                                alert_log.append(alert_key)
                                save_log(alert_log)

        with t3:
            st.header("▶️ 유효기간 365일 미만 의약품 목록")
            alert_log = load_log()
            lim_365 = current_date + timedelta(days=365)
            if '유효기간_날짜' in df_inventory.columns:
                s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & (df_inventory['유효기간_날짜'] <= lim_365) & (df_inventory['재고수량'] > 0)]
                for idx, row in s_exp.sort_values(by='유효기간_날짜').iterrows():
                    rem_d = (row['유효기간_날짜'] - current_date).days
                    if rem_d < 180: 
                        st.error(f"💥 **[초긴급 - 180일 미만]** **{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {row['유효기간_표시']} (**{rem_d}일 남음**)")
                        # 알림 로직
                        alert_key = f"exp_{row['제품명']}"
                        if alert_key not in alert_log:
                            send_telegram(f"🚨 [유효기간 임박]\n{row['제품명']}\n유효기간 {rem_d}일 남음")
                            alert_log.append(alert_key)
                            save_log(alert_log)
                    else: 
                        st.warning(f"⚠️ **[주의 - 1년 미만]** **{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {row['유효기간_표시']} ({rem_d}일 남음)")

        with t4:
            st.header("▶️ 90일 이상 장기 미출고 의약품")
            if not df_orders.empty and '출고일자' in df_orders.columns:
                df_l = df_orders.groupby('제품명')['출고일자'].max().reset_index()
                df_l.columns = ['제품명', '최종일']
                df_chk = pd.merge(df_inventory, df_l, on='제품명', how='left')
                df_chk = df_chk[df_chk['재고수량'] > 0].copy()
                df_chk['경과일'] = (current_date - df_chk['최종일']).dt.days
                df_chk['기록없음'] = df_chk['최종일'].isna()
                lim_90 = current_date - timedelta(days=90)
                df_filtered = df_chk[df_chk['기록없음'] | (df_chk['최종일'] <= lim_90)].copy()
                if not df_filtered.empty:
                    df_filtered = df_filtered.sort_values(by=['기록없음', '경과일'], ascending=[False, False])
                    for idx, row in df_filtered.iterrows():
                        yuhyo = row['유효기간_표시'] if '유효기간_표시' in row and str(row['유효기간_표시']) != 'nan' else "기록없음"
                        if row['기록없음']:
                            st.info(f"**{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {yuhyo} • 출고 기록 없음")
                        else:
                            st.info(f"**{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {yuhyo} • 최종일: {row['최종일'].strftime('%Y-%m-%d')} (**{int(row['경과일'])}일 경과**)")

        with t5:
            st.header("▶️ 창고 전체 현재 재고 현황")
            df_f = df_inventory[['제품명', '재고수량', '유효기간_표시']].copy()
            df_f.columns = ['제품명', '재고 수량 (개)', '유효기간']
            df_f = df_f.sort_values(by='제품명').reset_index(drop=True)
            
            st.markdown("### 🔍 의약품 찾기")
            p_search = st.text_input("조회하고 싶은 의약품명을 입력하세요:", "", key="p_search")
            df_f_disp = df_f.copy()
            if p_search: df_f_disp = df_f_disp[df_f_disp['제품명'].str.contains(p_search, case=False, na=False)]
            
            df_f_disp.insert(0, "선택", False)
            st.markdown("### 📋 창고 전체 재고 리스트")
            edited_df = st.data_editor(df_f_disp, column_config={"선택": st.column_config.CheckboxColumn(required=True)}, use_container_width=True, hide_index=True)
            
            selected_rows = edited_df[edited_df["선택"] == True]
            if not selected_rows.empty:
                selected_product = selected_rows.iloc[0]['제품명']
                st.markdown("---")
                st.subheader(f"📊 [{selected_product}] 거래처별 출고 이력 상세 결과")
                df_p_ord = df_orders[df_orders['제품명'] == selected_product].copy()
                if not df_p_ord.empty:
                    df_h = df_p_ord[['매출처', '출고일자', '수량']].copy()
                    df_h['출고일자'] = df_h['출고일자'].dt.strftime('%Y-%m-%d')
                    st.dataframe(df_h, use_container_width=True, hide_index=True)
                    csv_data = df_h.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(label=f"💾 {selected_product} 출고 이력 다운로드", data=csv_data, file_name=f"{selected_product}_출고이력.csv", mime="text/csv")
                else:
                    st.warning("✨ 해당 의약품은 최근 출고 기록이 없습니다.")
else:
    st.error("데이터 파일을 찾을 수 없습니다.")