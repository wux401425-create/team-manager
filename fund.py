import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import requests
import json
import re

# ================= 1. 核心配置 =================
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Team_Data_Center" 
TAB_PORTFOLIO = "Fund_Portfolio" 
TAB_SIP = "SIP_Config" # 新增：存放定投配置

def get_beijing_time():
    utc = datetime.utcnow()
    bj = utc + timedelta(hours=8)
    return bj.strftime("%Y-%m-%d"), bj.strftime("%H:%M")

def get_today_str():
    return get_beijing_time()[0]

# ================= 2. 谷歌连接 & 数据接口 =================
@st.cache_resource
def get_db_connection():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e: return None

# 加载数据 (同时加载持仓表和定投表)
def load_data():
    sh = get_db_connection()
    if not sh: return pd.DataFrame(), pd.DataFrame()
    try:
        # 1. 读取持仓
        try: ws_p = sh.worksheet(TAB_PORTFOLIO)
        except: 
            ws_p = sh.add_worksheet(title=TAB_PORTFOLIO, rows=100, cols=20)
            ws_p.update([["code", "name", "shares", "avg_cost", "proxy_code"]])
        
        raw_p = ws_p.get_all_values()
        if not raw_p: df_p = pd.DataFrame(columns=["code", "name", "shares", "avg_cost", "proxy_code"])
        else:
            headers = raw_p[0]
            if "proxy_code" not in headers: headers.append("proxy_code") # 兼容旧表
            df_p = pd.DataFrame(raw_p[1:], columns=headers) if len(raw_p)>1 else pd.DataFrame(columns=headers)
        
        # 2. 读取定投配置 (SIP)
        try: ws_s = sh.worksheet(TAB_SIP)
        except:
            ws_s = sh.add_worksheet(title=TAB_SIP, rows=50, cols=10)
            ws_s.update([["fund_code", "daily_amount", "last_run_date", "status"]]) # status: ON/OFF
            
        raw_s = ws_s.get_all_values()
        if not raw_s: df_s = pd.DataFrame(columns=["fund_code", "daily_amount", "last_run_date", "status"])
        else: df_s = pd.DataFrame(raw_s[1:], columns=raw_s[0])
            
        return df_p, df_s
    except: return pd.DataFrame(), pd.DataFrame()

# 保存数据 (通用)
def save_data(tab_name, df):
    sh = get_db_connection()
    if not sh: return False
    try:
        try: ws = sh.worksheet(tab_name)
        except: ws = sh.add_worksheet(title=tab_name, rows=100, cols=20)
        ws.clear()
        if df.empty: ws.update([df.columns.values.tolist()])
        else: ws.update([df.columns.values.tolist()] + df.astype(str).values.tolist())
        return True
    except: return False

# 接口: 获取官方净值 (用于计算定投份额)
def get_official_nav(fund_code):
    url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    try:
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            match = re.search(r'jsonpgz\((.*?)\);', r.text)
            if match:
                data = json.loads(match.group(1))
                return {"nav": float(data['dwjz']), "date": data['jzrq'], "name": data['name']}
    except: pass
    return None

# 接口: 影子实时涨跌
def get_proxy_rate(proxy_code):
    if not proxy_code or len(proxy_code) < 6: return 0.0
    url = f"http://hq.sinajs.cn/list={proxy_code}"
    try:
        headers = {"Referer": "https://finance.sina.com.cn"}
        r = requests.get(url, headers=headers, timeout=2)
        if r.status_code == 200:
            data = r.text.split(",")
            if len(data) > 3:
                yesterday = float(data[2])
                current = float(data[3])
                if current == 0: current = yesterday
                if yesterday == 0: return 0.0
                return ((current - yesterday) / yesterday) * 100
    except: pass
    return 0.0

# ================= 3. 页面主程序 =================
st.set_page_config(page_title="智能资产看板", page_icon="📈", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 私人资产看板")
    pwd = st.text_input("密码", type="password")
    if st.button("解锁"):
        if pwd == "8888": 
            st.session_state.auth = True
            st.rerun()
        else: st.error("密码错误")
else:
    bj_date, bj_time = get_beijing_time()
    df_fund, df_sip = load_data()
    
    # --- 1. 智能定投检查 (Auto-SIP Check) ---
    # 逻辑：检查上次执行日期和今天之间，有多少个工作日
    sip_pending_msg = []
    sip_execution_plan = [] # 存储待执行计划
    
    if not df_sip.empty and not df_fund.empty:
        today_dt = datetime.strptime(bj_date, "%Y-%m-%d").date()
        
        for idx, row in df_sip.iterrows():
            if row["status"] != "ON": continue
            
            f_code = str(row["fund_code"])
            amt = float(row["daily_amount"])
            last_run = row["last_run_date"]
            
            if not last_run: # 第一次设置，今天不算，下次算
                continue
                
            last_run_dt = datetime.strptime(last_run, "%Y-%m-%d").date()
            
            # 计算相差天数
            delta = (today_dt - last_run_dt).days
            if delta > 0:
                # 遍历中间的每一天
                missed_days = 0
                for i in range(1, delta + 1):
                    check_day = last_run_dt + timedelta(days=i)
                    # 关键逻辑：排除周六(5)和周日(6)
                    if check_day.weekday() < 5: 
                        missed_days += 1
                
                if missed_days > 0:
                    # 找到对应的基金名称
                    f_name = "未知基金"
                    found_f = df_fund[df_fund["code"] == f_code]
                    if not found_f.empty: f_name = found_f.iloc[0]["name"]
                    
                    total_amt = missed_days * amt
                    sip_pending_msg.append(f"• **{f_name} ({f_code})**: 补扣 {missed_days} 天 (共 ¥{total_amt:,.0f})")
                    
                    sip_execution_plan.append({
                        "code": f_code,
                        "add_amt": total_amt,
                        "days_count": missed_days,
                        "sip_idx": idx # 记录定投表里的行号，方便更新日期
                    })

    # 如果有待执行的定投，显示在最显眼的地方
    if sip_pending_msg:
        with st.container(border=True):
            st.markdown("### 🔔 定投补单提醒")
            st.info("检测到您有未执行的定投计划（已自动跳过周末）：")
            for msg in sip_pending_msg: st.write(msg)
            
            c_exec1, c_exec2 = st.columns([1, 4])
            if c_exec1.button("🚀 一键执行补单", type="primary"):
                # 执行补单逻辑
                logs = []
                for plan in sip_execution_plan:
                    code = plan["code"]
                    add_money = plan["add_amt"]
                    
                    # 获取当前最新净值作为成交价 (这是补单的折中方案)
                    info = get_official_nav(code)
                    if info:
                        nav = info['nav']
                        
                        # 更新持仓表
                        f_idx_list = df_fund[df_fund["code"] == code].index
                        if len(f_idx_list) > 0:
                            f_idx = f_idx_list[0]
                            old_shares = float(df_fund.at[f_idx, "shares"] or 0)
                            old_cost = float(df_fund.at[f_idx, "avg_cost"] or 0)
                            
                            new_shares_add = add_money / nav
                            total_shares = old_shares + new_shares_add
                            total_cost_val = (old_shares * old_cost) + add_money
                            new_avg_cost = total_cost_val / total_shares
                            
                            df_fund.at[f_idx, "shares"] = total_shares
                            df_fund.at[f_idx, "avg_cost"] = new_avg_cost
                            
                            # 更新定投表的日期为今天
                            df_sip.at[plan["sip_idx"], "last_run_date"] = bj_date
                            
                            logs.append(f"{code} 成功买入 {add_money}元，成本更新为 {new_avg_cost:.4f}")
                        else:
                            logs.append(f"错误：持仓表中找不到 {code}，请先建仓")
                
                # 保存
                save_data(TAB_PORTFOLIO, df_fund)
                save_data(TAB_SIP, df_sip)
                st.success("✅ 所有定投已执行！")
                st.session_state.logs = logs
                time.sleep(2)
                st.rerun()

    # --- 标题与刷新 ---
    c_t, c_r = st.columns([3, 1])
    with c_t: st.subheader(f"📈 智能资产看板")
    with c_r: 
        if st.button("🔄 刷新数据"): st.rerun()

    # --- 2. 主表格计算逻辑 ---
    total_market = 0.0
    total_cost = 0.0
    total_day_profit = 0.0
    table_data = []

    if not df_fund.empty:
        for i, row in df_fund.iterrows():
            code = str(row["code"]).zfill(6)
            proxy = str(row["proxy_code"]).strip()
            shares = float(row["shares"] or 0)
            avg_cost = float(row["avg_cost"] or 0)
            
            # 官方净值
            off_info = get_official_nav(code)
            nav_base = avg_cost
            if off_info: nav_base = off_info['nav']
            
            # 判断逻辑：官方净值日期是否是今天
            is_updated = (off_info and off_info['date'] == bj_date)
            
            if is_updated:
                # 盘后模式
                real_price = nav_base
                source = "✅ 官方净值"
                day_rate = 0.0 # 盘后暂不显示涨幅，只看盈亏
                day_profit = 0.0 # 难算，略过
            else:
                # 盘中模式
                proxy_rate = get_proxy_rate(proxy)
                day_rate = proxy_rate
                real_price = nav_base * (1 + day_rate/100)
                source = f"⚡ 影子({proxy})" if proxy else "⚠️ 无影子"
                day_profit = (real_price - nav_base) * shares

            # 汇总
            m_val = real_price * shares
            c_val = avg_cost * shares
            t_profit = m_val - c_val
            
            total_market += m_val
            total_cost += c_val
            total_day_profit += day_profit
            
            table_data.append({
                "基金名称": f"{row['name']}\n({code})",
                "成本价": avg_cost, # 用户要的对比列
                "今日估值": real_price, # 用户要的对比列
                "涨幅": f"{day_rate:+.2f}%",
                "今日盈亏": day_profit,
                "总盈亏": t_profit,
                "收益率": f"{(t_profit/c_val)*100:.2f}%" if c_val>0 else "0%",
                "数据源": source
            })

    # --- 3. 资产驾驶舱 ---
    ret_rate = (total_market - total_cost)/total_cost*100 if total_cost>0 else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("总持仓", f"¥{total_market:,.0f}")
    k2.metric("今日预估", f"¥{total_day_profit:,.0f}", delta=f"{total_day_profit:,.0f}", delta_color="inverse")
    k3.metric("总盈亏", f"¥{(total_market-total_cost):,.0f}", delta_color="inverse")
    k4.metric("总收益率", f"{ret_rate:+.2f}%")

    st.divider()

    # --- 4. 持仓明细表 (按用户需求调整列顺序) ---
    if table_data:
        st.dataframe(
            pd.DataFrame(table_data),
            use_container_width=True,
            column_config={
                "成本价": st.column_config.NumberColumn(format="%.4f", help="你的持仓成本"),
                "今日估值": st.column_config.NumberColumn(format="%.4f", help="基于影子涨幅的预估单价"),
                "今日盈亏": st.column_config.NumberColumn(format="¥%.2f"),
                "总盈亏": st.column_config.NumberColumn(format="¥%.2f"),
                "收益率": st.column_config.TextColumn(),
            },
            hide_index=True
        )

    st.divider()

    # --- 5. 操作与设置区 ---
    tab_buy, tab_sip, tab_new = st.tabs(["💰 单笔加仓", "📅 定投计划设置", "⚙️ 建仓/管理"])
    
    with tab_buy:
        c1, c2, c3 = st.columns([2, 1, 1])
        if not df_fund.empty:
            sel_fund = c1.selectbox("选择基金", df_fund["code"] + " - " + df_fund["name"])
            buy_amt = c2.number_input("买入金额", step=100.0)
            deal_nav = c3.number_input("成交净值 (或估值)", format="%.4f")
            if st.button("确认加仓"):
                code = sel_fund.split(" - ")[0]
                idx = df_fund[df_fund["code"]==code].index[0]
                
                old_s = float(df_fund.at[idx, "shares"])
                old_c = float(df_fund.at[idx, "avg_cost"])
                
                add_s = buy_amt / deal_nav
                new_s = old_s + add_s
                new_c = ((old_s * old_c) + buy_amt) / new_s
                
                df_fund.at[idx, "shares"] = new_s
                df_fund.at[idx, "avg_cost"] = new_c
                save_data(TAB_PORTFOLIO, df_fund)
                st.success(f"加仓成功！新成本: {new_c:.4f}")
                time.sleep(1)
                st.rerun()

    with tab_sip:
        st.caption("设置这里的计划后，每次打开网页，系统会自动检查是否需要补扣（自动跳过周末）。")
        if not df_fund.empty:
            c_s1, c_s2, c_s3 = st.columns([2, 1, 1])
            s_fund = c_s1.selectbox("选择定投基金", df_fund["code"] + " - " + df_fund["name"], key="sip_sel")
            s_amt = c_s2.number_input("每日定投金额 (元)", value=100.0, step=50.0)
            
            if c_s3.button("➕ 开启定投"):
                s_code = s_fund.split(" - ")[0]
                # 检查是否已有
                exist_s = df_sip[df_sip["fund_code"] == s_code]
                if not exist_s.empty:
                    s_idx = exist_s.index[0]
                    df_sip.at[s_idx, "daily_amount"] = s_amt
                    df_sip.at[s_idx, "status"] = "ON"
                    df_sip.at[s_idx, "last_run_date"] = bj_date # 重置其实日期为今天
                    st.success(f"已更新 {s_code} 的定投计划！")
                else:
                    new_sip = {"fund_code": s_code, "daily_amount": s_amt, "last_run_date": bj_date, "status": "ON"}
                    df_sip = pd.concat([df_sip, pd.DataFrame([new_sip])], ignore_index=True)
                    st.success(f"已新建 {s_code} 定投计划！")
                
                save_data(TAB_SIP, df_sip)
                time.sleep(1)
                st.rerun()
            
            # 显示现有计划
            if not df_sip.empty:
                st.markdown("#### 📋 正在执行的计划")
                st.dataframe(df_sip, use_container_width=True)
                if st.button("🛑 停止/删除所有定投"):
                    save_data(TAB_SIP, pd.DataFrame(columns=df_sip.columns))
                    st.rerun()

    with tab_new:
        with st.expander("建仓 / 修改基金信息"):
            cc1, cc2, cc3, cc4 = st.columns(4)
            n_c = cc1.text_input("代码", max_chars=6)
            n_p = cc2.text_input("影子代码 (如 sh510300)")
            n_s = cc3.number_input("份额", format="%.2f")
            n_cost = cc4.number_input("成本", format="%.4f")
            n_n = st.text_input("名称")
            if st.button("保存基金"):
                if n_c:
                    exist = df_fund[df_fund["code"]==n_c]
                    if not exist.empty:
                        idx = exist.index[0]
                        df_fund.at[idx, "proxy_code"] = n_p
                        df_fund.at[idx, "shares"] = n_s
                        df_fund.at[idx, "avg_cost"] = n_cost
                        if n_n: df_fund.at[idx, "name"] = n_n
                    else:
                        df_fund = pd.concat([df_fund, pd.DataFrame([{"code":n_c, "name":n_n, "shares":n_s, "avg_cost":n_cost, "proxy_code":n_p}])], ignore_index=True)
                    save_data(TAB_PORTFOLIO, df_fund)
                    st.rerun()
