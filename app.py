# --- [탭 1] 매출처 선택 리스트 ---
        with t1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            if not df_orders.empty and '매출처' in df_orders.columns:
                u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
                df_cust = pd.DataFrame(u_cust, columns=['매출처'])
                c_search = st.text_input("🔍 매출처 검색:", "", key="c_search_t1")
                if c_search: df_cust = df_cust[df_cust['매출처'].str.contains(c_search, case=False, na=False)]
                
                df_cust.insert(0, "선택", False)
                # 체크박스 너비를 50으로 고정하여 캡쳐 화면처럼 비율을 맞춥니다.
                edited_df1 = st.data_editor(
                    df_cust, 
                    column_config={"선택": st.column_config.CheckboxColumn(required=True, width=50)}, 
                    use_container_width=True, hide_index=True
                )
                
                sel1 = edited_df1[edited_df1["선택"] == True]
                if not sel1.empty:
                    s_cust = sel1.iloc[0]['매출처']
                    st.markdown(f"### 📅 [{s_cust}] 상세 내역")
                    df_c = df_orders[df_orders['매출처'] == s_cust].sort_values('출고일자', ascending=False)
                    st.dataframe(df_c[['출고일자', '제품명', '수량']], use_container_width=True, hide_index=True)

        # --- [탭 5] 전체 현재 재고 ---
        with t5:
            st.header("▶️ 창고 전체 현재 재고 현황")
            df_f = df_inventory[['제품명', '재고수량', '유효기간_표시']].copy()
            df_f.columns = ['제품명', '재고 수량 (개)', '유효기간']
            df_f = df_f.sort_values(by='제품명').reset_index(drop=True)
            
            p_search = st.text_input("🔍 품목명 검색:", "", key="p_search")
            if p_search: df_f = df_f[df_f['제품명'].str.contains(p_search, case=False, na=False)]
            
            df_f.insert(0, "선택", False)
            # 체크박스 너비를 50으로 고정하여 캡쳐 화면처럼 비율을 맞춥니다.
            edited_df5 = st.data_editor(
                df_f, 
                column_config={"선택": st.column_config.CheckboxColumn(required=True, width=50)}, 
                use_container_width=True, hide_index=True
            )
            
            sel5 = edited_df5[edited_df5["선택"] == True]
            if not sel5.empty:
                target = sel5.iloc[0]['제품명']
                st.markdown(f"### 📊 [{target}] 거래처별 출고 이력")
                df_p = df_orders[df_orders['제품명'] == target].sort_values('출고일자', ascending=False)
                st.dataframe(df_p[['매출처', '출고일자', '수량']], use_container_width=True, hide_index=True)