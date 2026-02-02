import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import time

# ================= 1. 核心配置 =================
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Team_Data_Center" 

# 汉化映射
CN_MAP = {
    "date": "日期", "store": "店铺", "user": "负责人", 
    "task": "任务内容", "status": "状态", "time": "完成时间",
    "uid": "工号", "name": "姓名", "pwd": "密码", "role": "角色", "tasks": "固定职责"
}
EN_MAP = {v: k for k, v in CN_MAP.items()}

# 北京时间
def get_beijing_time():
    utc = datetime.utcnow()
    bj = utc + timedelta(hours=8)
    return bj.strftime("%Y-%m-%d"), bj.strftime("%H:%M")

# ================= 2. 谷歌引擎 (缓存加速) =================
@st.cache_resource
def get_db_connection():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        return None

# 缓存表格列表 10分钟
@st.cache_data(ttl=600)
def get_all_sheet_titles():
    sh = get_db_connection()
    if not sh: return []
    try:
        return [ws.title for ws in sh.worksheets()]
    except:
        return []

# 读取数据 10分钟缓存
@st.cache_data(ttl=600)
def load_data(tab_name, default_cols=[]):
    sh = get_db_connection()
    if not sh: return pd.DataFrame(columns=default_cols)
    try:
        worksheet = sh.worksheet(tab_name)
        raw = worksheet.get_all_values()
        if not raw: return pd.DataFrame(columns=default_cols)
        
        headers = raw[0]
        rows = raw[1:]
        df = pd.DataFrame(rows, columns=headers) if rows else pd.DataFrame(columns=headers)
        
        for c in default_cols:
            if c not in df.columns: df[c] = ""
        return df.astype(str)
    except:
        return pd.DataFrame(columns=default_cols)

# 保存数据 (带加载动画)
def save_data(tab_name, df):
    sh = get_db_connection()
    if not sh: return False
    try:
        with st.spinner('☁️ 正在同步到云端...'):
            try:
                ws = sh.worksheet(tab_name)
            except:
                ws = sh.add_worksheet(title=tab_name, rows=100, cols=20)
            ws.clear()
            if df.empty:
                ws.update([df.columns.values.tolist()])
            else:
                ws.update([df.columns.values.tolist()] + df.astype(str).values.tolist())
            
            # 强制刷新缓存
            load_data.clear()
            get_all_sheet_titles.clear() 
            return True
    except Exception as e:
        st.error(f"网络超时，请重试: {e}")
        return False

# 辅助函数
def try_float(x):
    try: return float(str(x).replace('¥','').replace('$','').replace(',','').strip())
    except: return 0.0

def get_permissions():
    df = load_data("Permissions", ["table_name", "allowed_uids"])
    perms = {}
    if not df.empty:
        for _, r in df.iterrows():
            perms[r["table_name"]] = str(r["allowed_uids"]).split(",")
    return perms

def save_permissions(t_name, uids):
    df = load_data("Permissions", ["table_name", "allowed_uids"])
    df = df[df["table_name"] != t_name]
    new_r = {"table_name": t_name, "allowed_uids": ",".join(uids)}
    save_data("Permissions", pd.concat([df, pd.DataFrame([new_r])], ignore_index=True))

# ================= 3. 页面主逻辑 =================
st.set_page_config(page_title="团队协作系统", layout="wide")

# 登录状态检查
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_info' not in st.session_state: st.session_state.user_info = {}

# Token 自动登录
token = st.query_params.get("token", None)
if not st.session_state.logged_in and token:
    u_df = load_data("Users", ["uid", "name", "pwd", "role"])
    if not u_df.empty:
        me = u_df[u_df["uid"] == token]
        if not me.empty:
            st.session_state.logged_in = True
            st.session_state.user_info = me.iloc[0].to_dict()

# 登录界面
if not st.session_state.logged_in:
    st.title("🚀 团队协作系统")
    u_df = load_data("Users", ["uid", "name", "pwd", "role"])
    if u_df.empty:
        # 初始化 Boss
        u_df = pd.DataFrame([{"uid": "u_boss", "name": "Boss", "pwd": "666", "role": "admin"}])
        save_data("Users", u_df)
    
    names = u_df["name"].tolist()
    c1, c2 = st.columns([2,1])
    with c1:
        s_name = st.selectbox("账号", names)
        pwd = st.text_input("密码", type="password")
        remember = st.checkbox("✅ 记住我 (免下次登录)")
        if st.button("登录系统", type="primary"):
            me = u_df[u_df["name"] == s_name].iloc[0]
            if str(me["pwd"]) == pwd:
                st.session_state.logged_in = True
                st.session_state.user_info = me.to_dict()
                if remember: st.query_params["token"] = me["uid"]
                st.rerun()
            else:
                st.error("密码错误")
else:
    # 登录后界面
    user = st.session_state.user_info
    is_admin = (user["role"] == "admin")
    bj_date, bj_time = get_beijing_time()
    
    with st.sidebar:
        st.info(f"👤 {user['name']} ({'管理员' if is_admin else '员工'})")
        st.caption(f"🕒 北京时间: {bj_time}")
        
        if st.button("🔄 刷新最新数据", type="primary"):
            load_data.clear()
            get_all_sheet_titles.clear()
            st.rerun()
        
        st.divider()
        pages = ["📦 任务管理"]
        
        # 获取可见表格
        all_tabs = get_all_sheet_titles()
        sys_tabs = ["Users", "Tasks", "Assignments", "Permissions", "Settings"]
        custom_tabs = [t for t in all_tabs if t not in sys_tabs]
        
        perms = get_permissions()
        vis_tabs = []
        for t in custom_tabs:
            # 如果是管理员，或者是被授权的员工
            if is_admin or (user["uid"] in perms.get(t, [])):
                vis_tabs.append(t)
        
        if vis_tabs:
            st.caption("我的协作表格")
            for t in vis_tabs: pages.append(f"📊 {t}")
            
        nav = st.radio("系统导航", pages)
        st.divider()
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.query_params.clear()
            st.rerun()

    # ================= 模块 1：任务管理 =================
    if nav == "📦 任务管理":
        st.subheader("📋 任务管理中心")
        tasks_df = load_data("Tasks", ["date", "store", "user", "task", "status", "time"])
        assign_df = load_data("Assignments", ["store", "uid", "tasks"])
        users_df = load_data("Users", ["uid", "name", "pwd", "role"])
        all_names = users_df["name"].tolist()
        
        if is_admin:
            # === 管理员视图 ===
            t1, t2, t3 = st.tabs(["⚡ 派单控制台", "📝 任务记录总表", "👥 人员管理"])
            
            with t1:
                st.markdown("##### 1️⃣ 每日日常任务 (基于岗位配置)")
                c_gen, c_clear = st.columns([1, 1])
                with c_gen:
                    if st.button("⚡ 一键发布今日日常任务"):
                        new_rows = []
                        for _, r in assign_df.iterrows():
                            runner = users_df[users_df["uid"]==r["uid"]]
                            if not runner.empty:
                                runner_name = runner.iloc[0]["name"]
                                lines = [x.strip() for x in str(r["tasks"]).split('\n') if x.strip()]
                                for l in lines:
                                    new_rows.append({"date": bj_date, "store": r["store"], "user": runner_name, "task": l, "status": "进行中", "time": "-"})
                        if new_rows:
                            save_data("Tasks", pd.concat([tasks_df, pd.DataFrame(new_rows)], ignore_index=True))
                            st.success("发布成功")
                            st.rerun()
                with c_clear:
                    if st.button("🗑️ 清空所有任务历史"):
                        save_data("Tasks", pd.DataFrame(columns=tasks_df.columns))
                        st.rerun()

                st.divider()
                st.markdown("##### 2️⃣ 临时加塞任务")
                with st.container(border=True):
                    c_tmp1, c_tmp2, c_tmp3 = st.columns([1, 1, 2])
                    t_store = c_tmp1.text_input("店铺名", value="通用")
                    t_who = c_tmp2.selectbox("指派给", all_names)
                    t_content = c_tmp3.text_input("任务内容")
                    if st.button("➕ 发布临时任务"):
                        if t_content:
                            new_r = {"date": bj_date, "store": t_store, "user": t_who, "task": t_content, "status": "进行中", "time": "-"}
                            save_data("Tasks", pd.concat([tasks_df, pd.DataFrame([new_r])], ignore_index=True))
                            st.success("已发布")
                            st.rerun()

                st.divider()
                st.markdown("##### 3️⃣ 固定岗位配置")
                # 转换显示
                uid_to_name = dict(zip(users_df["uid"], users_df["name"]))
                name_to_uid = dict(zip(users_df["name"], users_df["uid"]))
                
                view_assign = assign_df.copy()
                view_assign["uid"] = view_assign["uid"].map(uid_to_name)
                view_assign = view_assign.rename(columns=CN_MAP)
                
                edited_assign = st.data_editor(view_assign, num_rows="dynamic", use_container_width=True)
                
                if st.button("💾 保存岗位配置"):
                    save_assign = edited_assign.rename(columns=EN_MAP)
                    save_assign["uid"] = save_assign["uid"].map(name_to_uid)
                    save_assign = save_assign.dropna(subset=["uid"])
                    save_data("Assignments", save_assign)
                    st.success("配置已保存")

            with t2:
                # 任务总表
                view_tasks = tasks_df.rename(columns=CN_MAP)
                st.dataframe(view_tasks, use_container_width=True)

            with t3:
                # 人员表
                view_users = users_df.rename(columns=CN_MAP)
                edited_users = st.data_editor(
                    view_users, num_rows="dynamic",
                    column_config={"工号(自动)": st.column_config.TextColumn(disabled=True), "角色": st.column_config.SelectboxColumn(options=["admin", "staff"])}
                )
                if st.button("💾 保存人员名单"):
                    save_users = edited_users.rename(columns=EN_MAP)
                    for i in range(len(save_users)):
                        if not save_users.iloc[i]["uid"]: save_users.at[i, "uid"] = f"u_{str(uuid.uuid4())[:6]}"
                    save_data("Users", save_users)
                    st.success("人员表已更新")
                    st.rerun()
        else:
            # === 员工视图 ===
            st.caption(f"📅 今日任务 ({bj_date})")
            my_tasks = tasks_df[tasks_df["user"] == user["name"]]
            
            # 待办任务
            pending = my_tasks[my_tasks["status"] == "进行中"]
            completed = my_tasks[my_tasks["status"] == "完成"]
            
            if not pending.empty:
                st.markdown("#### 🔥 待办事项")
                for idx, row in pending.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 5, 2])
                        c1.markdown(f"**🏬 {row['store']}**")
                        c2.write(row['task'])
                        if c3.button("✅ 完成打卡", key=f"k_{idx}"):
                            tasks_df.at[idx, "status"] = "完成"
                            tasks_df.at[idx, "time"] = bj_time
                            save_data("Tasks", tasks_df)
                            st.rerun()
            else:
                st.info("👍 你真棒！所有待办任务都完成了。")

            if not completed.empty:
                st.markdown("#### ✅ 已完成")
                st.dataframe(completed.rename(columns=CN_MAP), use_container_width=True)

    # ================= 模块 2：自定义表格 (协作核心) =================
    elif nav.startswith("📊"):
        t_name = nav.replace("📊 ", "")
        st.subheader(f"📝 {t_name}")
        df = load_data(t_name)
        
        # --- 仅老板可见的设置区 ---
        if is_admin:
            with st.expander("⚙️ 管理员设置 (权限/计算器/导入)"):
                t_perm, t_calc, t_imp = st.tabs(["🔒 权限", "🧮 计算器", "📤 导入Excel"])
                
                with t_perm:
                    all_u = load_data("Users", ["uid", "name"])
                    staffs = all_u[all_u["role"]!="admin"]
                    curr = get_permissions().get(t_name, [])
                    sel = st.multiselect("勾选允许查看/编辑的员工", staffs["uid"].tolist(), default=[u for u in curr if u in staffs["uid"].tolist()], format_func=lambda x: staffs[staffs["uid"]==x]["name"].values[0])
                    if st.button("保存权限设置"):
                        save_permissions(t_name, sel)
                        st.success("已保存")
                
                with t_calc:
                    st.caption("公式示例: `(售价 - 成本) * 汇率`")
                    c1, c2 = st.columns([3, 1])
                    fma = c1.text_input("计算公式")
                    res_col = c1.text_input("结果存入列名", value="计算结果")
                    if c2.button("执行计算"):
                        if fma:
                            try:
                                tmp = df.copy()
                                for c in df.columns: tmp[c] = tmp[c].apply(try_float)
                                df[res_col] = tmp.eval(fma).round(2).astype(str)
                                save_data(t_name, df)
                                st.success("计算完成")
                                st.rerun()
                            except Exception as e:
                                st.error(f"公式错误: {e}")

                with t_imp:
                    st.warning("⚠️ 警告：导入将覆盖当前表格所有内容")
                    up = st.file_uploader("上传 Excel/CSV", type=['xlsx', 'csv'])
                    if up and st.button("确认覆盖导入"):
                        try:
                            if up.name.endswith('.csv'): idf = pd.read_csv(up)
                            else: idf = pd.read_excel(up)
                            save_data(t_name, idf.astype(str))
                            st.success("导入成功")
                            st.rerun()
                        except Exception as e:
                            st.error(f"失败: {e}")
        
        # --- 协作编辑区 (所有人可见) ---
        if not df.empty and len(df.columns)>0:
            # 所有人都能看见编辑器
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"ed_{t_name}")
            
            c_sv, c_del = st.columns([4,1])
            # 所有人都能保存
            if c_sv.button("💾 保存修改", type="primary"):
                if save_data(t_name, edited):
                    st.success("✅ 保存成功！同事们刷新后也能看到你的修改。")
            
            # 只有老板能删除表
            if is_admin and c_del.button("🗑️ 删除此表"):
                get_db_connection().del_worksheet(get_db_connection().worksheet(t_name))
                get_all_sheet_titles.clear()
                st.rerun()
        else:
            st.info("📭 这是一个空表，请老板导入数据。")

    # 新建表 (仅老板)
    if is_admin:
        with st.sidebar:
            st.divider()
            with st.expander("➕ 新建表格"):
                nn = st.text_input("表名")
                if st.button("创建"):
                    if nn and nn not in all_tabs:
                        save_data(nn, pd.DataFrame(columns=["A"]))
                        st.rerun()
