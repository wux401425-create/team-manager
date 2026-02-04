import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import requests
import re

# ================= 1. 核心配置 =================
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Team_Data_Center" 
TAB_NAME = "Fund_Portfolio" 

def get_beijing_time():
    utc = datetime.utcnow()
    bj = utc + timedelta(hours=8)
    return bj.strftime("%Y-%m-%d"), bj.strftime("%H:%M")

# ================= 2. 谷歌连接 & 新浪实时接口 =================
@st.cache_resource
def get_db_connection():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e: return None

def load_data():
    sh = get_db_connection()
    if not sh: return pd.DataFrame()
    try:
        try: worksheet = sh.worksheet(TAB_NAME)
        except: 
            worksheet = sh.add_worksheet(title=TAB_NAME, rows=100, cols=20)
            # 增加了一列 proxy_code (影子代码)
            worksheet.update([["code", "name", "shares", "avg_cost", "proxy_code"]]) 
        
        raw = worksheet.get_all_values()
        if not raw: return pd.DataFrame(columns=["code", "name", "shares", "avg_cost", "proxy_code"])
        
        headers = raw[0]
        # 兼容旧表头，如果没有 proxy_code 自动补上
        if "proxy_code" not in headers:
            headers.append("proxy_code")
            # 这里的逻辑稍微复杂点，为了兼容性，简单处理：
            rows = raw[1:]
            df = pd.DataFrame(rows, columns=raw[0])
            df["proxy_code"] = ""
            return df
            
        rows = raw[1:]
        df = pd.DataFrame(rows, columns=headers) if rows else pd.DataFrame(columns=headers)
        return df
    except: return pd.DataFrame()

def save_data(df):
    sh = get_db_connection()
    if not sh: return False
    try:
        with st.spinner('☁️ 数据同步中...'):
            try: ws = sh.worksheet(TAB_NAME)
            except: ws = sh.add_worksheet(title=TAB_NAME, rows=100, cols=20)
            ws.clear()
            if df.empty: ws.update([df.columns.values.tolist()])
            else: ws.update([df.columns.values.tolist()] + df.astype(str).values.tolist())
            return True
    except: return False

# ⭐⭐⭐ 核心：获取影子代码的实时涨跌 (新浪接口) ⭐⭐⭐
def get_realtime_proxy(proxy_code):
    # proxy_code 示例: sh512690 (酒ETF) 或 sz159915 (创业板)
    if not proxy_code or len(proxy_code) < 6:
        return 0.0, 0.0 # 没填代码，返回0
        
    url = f"http://hq.sinajs.cn/list={proxy_code}"
    try:
        headers = {"Referer": "https://finance.sina.com.cn"}
        r = requests.get(url, headers=headers, timeout=2)
        # 返回格式：var hq_str_sh512690="酒ETF,0.766,0.767,0.756,..."
        # 索引：1=开盘, 2=昨日收盘, 3=当前价格
        if r.status_code == 200:
            content = r.text
            if "," in content:
                data = content.split(",")
                if len(data) > 3:
                    yesterday = float(data[2])
                    current = float(data[3])
                    
                    # 如果还没开盘(current为0)，用昨日收盘价
                    if current == 0: current = yesterday
                    
                    # 计算涨跌幅
                    change_pct = ((current - yesterday) / yesterday) * 100
                    return change_pct, current
    except: pass
    return 0.0, 0.0

# ================= 3. 页面主程序 =================
st.set_page_config(page_title="实时投资指挥部", page_icon="📈", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 私人资产看板")
    pwd = st.text_input("请输入访问密码", type="password")
    if st.button("解锁"):
        if pwd == "8888": 
            st.session_state.auth = True
            st.rerun()
        else: st.error("密码错误")
else:
    bj_date, bj_time = get_beijing_time()
    
    # 顶部状态栏
    st.markdown(f"### 📈 实时实盘指挥部 <span style='font-size:14px;color:gray'>({bj_time})</span>", unsafe_allow_html=True)
    
    col_refresh, col_help = st.columns([1, 4])
    if col_refresh.button("🔄 立即刷新行情", type="primary"): st.rerun()
    
    # 读取数据
    fund_df = load_data()
    
    portfolio_data = []
    total_assets = 0.0
    total_profit_day = 0.0 # 今日预估
    total_profit_all = 0.0 # 总盈亏
    
    if not fund_df.empty:
        # 批量获取行情（为了速度，这里用循环，量大可优化）
        for i, row in fund_df.iterrows():
            code = str(row["code"])
            name = str(row["name"])
            shares = float(row["shares"] or 0)
            cost = float(row["avg_cost"] or 0)
            
            # 获取影子行情
            # 这里的逻辑是：如果没有填 proxy_code，涨幅就是 0
            proxy = str(row["proxy_code"]).strip()
            rate, current_price_proxy = get_realtime_proxy(proxy)
            
            # ⭐ 核心估算逻辑 ⭐
            # 因为不知道场外基金的净值，我们假设：
            # 实时净值 = 持仓成本 * (1 + 总收益率 + 今日涨跌) -- 这样算不准
            # 简易算法：我们只能算出“今日盈亏”，总金额只能按“昨日净值”或“成本”估算
            # 为了让你做决策，我们假设：当前净值 ≈ 成本 * (1 + 累计涨幅) -> 这里太复杂
            
            # ✅ 实用逻辑：
            # 我们只关心“今日赚了多少”和“现在大概多少钱”
            # 假设基准净值是 Cost (或者你需要手动更新昨日净值，为了自动化，我们先用 Cost + 影子涨幅来演示趋势)
            
            # 修正算法：
            # 1. 既然是“无头苍蝇”，我们更看重“涨跌幅”。
            # 2. 我们用 (成本价 * (1+影子涨跌幅/100)) 来模拟当前的瞬间变化是不对的，因为成本价是旧的。
            # 3. 妥协方案：用户需要看到的是【百分比】。
            
            # 显示数据
            est_val_change = shares * cost * (rate / 100) # 今日预估盈亏 = 持仓金额 * 影子涨幅
            est_current_amt = (shares * cost) + est_val_change # 预估当前持仓
            
            # 总盈亏 (这里因为无法获取准确净值，我们只能显示今日的变动对总资产的影响，或者你可以手动更新净值)
            # 为了简单，这里先只计算【今日】的动态。
            
            total_assets += est_current_amt
            total_profit_day += est_val_change
            
            # 判断颜色
            color = "🔴" if rate > 0 else "Hz" if rate < 0 else "⚪"
            
            portfolio_data.append({
                "基金": f"{name}\n({code})",
                "参考标的": proxy if proxy else "未绑定",
                "☁️ 实时涨幅": f"{rate:+.2f}%",  # 带正负号
                "持仓金额": shares * cost, # 原始本金
                "⚡ 今日预估": est_val_change,
                "份额": shares,
                "成本": cost,
            })
            
    # 资产大屏
    m1, m2 = st.columns(2)
    m1.metric("💰 预估总持仓", f"¥{total_assets:,.0f}")
    m2.metric("📈 今日战况 (预估)", f"¥{total_profit_day:,.0f}", delta=f"{total_profit_day:,.0f}", delta_color="inverse")

    # 列表展示
    if portfolio_data:
        df_show = pd.DataFrame(portfolio_data)
        st.dataframe(
            df_show, 
            use_container_width=True,
            column_config={
                "参考标的": st.column_config.TextColumn(help="sh=上海, sz=深圳. 例如 sh512690"),
                "☁️ 实时涨幅": st.column_config.TextColumn(help="基于参考标的的实时涨跌"),
                "⚡ 今日预估": st.column_config.NumberColumn(format="¥%.2f", help="基于本金的预估波动"),
                "持仓金额": st.column_config.NumberColumn(format="¥%.0f"),
            },
            hide_index=True
        )
    else:
        st.info("请在下方建仓，并绑定影子代码。")

    st.divider()
    
    # === 操作区 ===
    with st.expander("➕ 添加/修改基金 (绑定影子代码)", expanded=True):
        st.caption("🔍 影子代码怎么填？去炒股软件看。")
        st.caption("例：白酒基金 -> 填 `sh512690` (酒ETF)；纳斯达克 -> 填 `sh513100` (纳指ETF)；医疗 -> 填 `sz159929` (医药ETF)")
        
        c1, c2, c3, c4, c5 = st.columns(5)
        n_code = c1.text_input("基金代码 (如 000001)")
        n_name = c2.text_input("名称 (如 招商白酒)")
        n_proxy = c3.text_input("影子代码 (关键!)", placeholder="sh51xxxx")
        n_shares = c4.number_input("份额", step=100.0)
        n_cost = c5.number_input("成本价", format="%.4f")
        
        if st.button("💾 保存/更新"):
            if n_code:
                # 检查是否已存在
                existing = fund_df[fund_df["code"] == n_code]
                if not existing.empty:
                    # 更新
                    idx = existing.index[0]
                    fund_df.at[idx, "name"] = n_name
                    fund_df.at[idx, "proxy_code"] = n_proxy
                    fund_df.at[idx, "shares"] = n_shares
                    fund_df.at[idx, "avg_cost"] = n_cost
                else:
                    # 新增
                    new_row = {"code": n_code, "name": n_name, "shares": n_shares, "avg_cost": n_cost, "proxy_code": n_proxy}
                    fund_df = pd.concat([fund_df, pd.DataFrame([new_row])], ignore_index=True)
                
                save_data(fund_df)
                st.success("保存成功！")
                time.sleep(1)
                st.rerun()

    # 删除功能
    with st.expander("🗑️ 删除基金"):
        if not fund_df.empty:
            del_code = st.selectbox("选择要删除的", fund_df["code"].tolist())
            if st.button("确认删除"):
                fund_df = fund_df[fund_df["code"] != del_code]
                save_data(fund_df)
                st.rerun()
