import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import json

# ================= 1. Google Sheets 连接引擎 =================
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Team_Data_Center" 

def get_db_connection():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"连接失败，请检查 Secrets 配置: {e}")
        st.stop()

# 读取数据
def load_data(tab_name, default_cols=[]):
    sh = get_db_connection()
    try:
        worksheet = sh.worksheet(tab_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        # 补全缺失的列
        for col in default_cols:
            if col not in df.columns:
                df[col] = ""
        # 全部转为字符型，避免报错
        return df.astype(str)
    except gspread.WorksheetNotFound:
        # 如果表不存在，自动创建
        worksheet = sh.add_worksheet(title=tab_name, rows=100, cols=20)
        if default_cols:
            worksheet.append_row(default_cols)
        return pd.DataFrame(columns=default_cols)

# 保存数据 (覆盖模式)
def save_data(tab_name, df):
    sh = get_db_connection()
    try:
        worksheet = sh.worksheet(tab_name)
    except:
        worksheet = sh.add_worksheet(title=tab_name, rows=100, cols=20)
    worksheet.clear()
    # 写入表头和数据
    if not df.empty:
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
    else:
        # 如果是空表，至少写个表头
        worksheet.update([df.columns.values.tolist()])

# --- 权限管理辅助函数 ---
def get_permissions():
    df = load_data("Permissions", ["table_name", "allowed_uids"])
    perms = {}
    for _, row in df.iterrows():
        perms[row["table_name"]] = str(row["allowed_uids"]).split(",")
    return perms

def save_permissions(table_name, uid_list):
    df = load_data("Permissions", ["table_name", "allowed_uids"])
    # 移除旧记录
    df = df[df["table_name"] != table_name]
    # 添加新记录
    new_row = {"table_name": table_name, "allowed_uids": ",".join(uid_list)}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_data("Permissions", df)

# ================= 2. 默认配置 =================
DEFAULT_USERS = [
    {"uid": "u_boss", "name": "Boss", "pwd": "666", "role": "admin"},
]

st.set_page_config(page_title="Team ERP Pro", layout="wide")

# ================= 3. 登录逻辑 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🚀 团队系统 (Google同步版)")
    users_df = load_data("Users", ["uid", "name", "pwd", "role"])
    
    # 初始化默认用户
    if users_df.empty:
        users_df = pd.DataFrame(DEFAULT_USERS)
        save_data("Users", users_df)
    
    name_list = users_df["name"].tolist()
    selected_name = st.selectbox("选择角色", name_list)
    pwd = st.text_input("密码", type="password")
    
    if st.button("登录", type="primary"):
        user_row = users_df[users_df["name"] == selected_name].iloc[0]
        if str(user_row["pwd"]) == pwd:
            st.session_state.logged_in = True
            st.session_state.user_info = user_row.to_dict()
            st.rerun()
        else:
            st.error("密码错误")

else:
    # ================= 4. 主系统 =================
    user = st.session_state.user_info
    is_admin = (user["role"] == "admin")
    
    with st.sidebar:
        st.title(f"👋 {user['name']}")
        
        # 导航逻辑
        pages = ["📦 任务管理"]
        
        # 获取所有自定义表
        sh = get_db_connection()
        all_tabs = [ws.title for ws in sh.worksheets()]
        system_tabs = ["Users", "Tasks", "Assignments", "Permissions", "Settings"]
        custom_tabs = [t for t in all_tabs if t not in system_tabs]
        
        # 权限过滤
        perms = get_permissions()
        visible_tabs = []
        for t in custom_tabs:
            allowed = perms.get(t, [])
            # Boss可见所有，员工看授权
            if is_admin or (user["uid"] in allowed):
                visible_tabs.append(t)
                
        if visible_tabs:
            st.divider()
            st.caption("多平台数据库")
            for t in visible_tabs:
                pages.append(f"📊 {t}")
        
        selected_page = st.radio("导航", pages)
        
        # Boss 创建新表入口
        if is_admin:
            st.divider()
            with st.expander("➕ 创建新表格"):
                new_t_name = st.text_input("表名 (如: Temu成本)")
                if st.button("创建"):
                    if new_t_name and new_t_name not in all_tabs:
                        # 创建一个空表
                        sh.add_worksheet(title=new_t_name, rows=100, cols=20)
                        st.success("创建成功！")
                        st.rerun()
        
        st.divider()
        if st.button("退出"):
            st.session_state.logged_in = False
            st.rerun()

    # --- 任务管理 (保持不变) ---
    if selected_page == "📦 任务管理":
        st.title("📦 任务管理")
        tasks_df = load_data("Tasks", ["date", "store", "user", "task", "status", "time"])
        assign_df = load_data("Assignments", ["store", "uid", "tasks"])
        
        if is_admin:
            tab1, tab2, tab3 = st.tabs(["⚡ 派单", "🔗 分配", "⚙️ 人员管理"])
            with tab1:
                if st.button("⚡ 生成今日任务", type="primary"):
                    # ... (简化：派单逻辑同前) ...
                    today = datetime.now().strftime("%Y-%m-%d")
                    new_rows = []
                    users_df = load_data("Users", ["uid", "name"])
                    for _, row in assign_df.iterrows():
                        u_name_s = users_df[users_df["uid"] == row["uid"]]["name"]
                        if not u_name_s.empty:
                            lines = [t.strip() for t in str(row["tasks"]).split('\n') if t.strip()]
                            for l in lines:
                                new_rows.append({"date": today, "store": row["store"], "user": u_name_s.values[0], "task": l, "status": "进行中", "time": "-"})
                    if new_rows:
                        save_data("Tasks", pd.concat([tasks_df, pd.DataFrame(new_rows)], ignore_index=True))
                        st.success("派单成功")
                        st.rerun()
                st.dataframe(tasks_df, use_container_width=True)
            
            with tab2:
                # 分配逻辑
                users_df = load_data("Users", ["uid", "name"])
                name_map = dict(zip(users_df["name"], users_df["uid"]))
                # 预处理数据以显示名字
                display_df = assign_df.copy()
                # 简单处理：这里直接显示编辑器，保存时转换
                edited = st.data_editor(assign_df, num_rows="dynamic", use_container_width=True)
                if st.button("💾 保存分配"):
                    save_data("Assignments", edited)
                    st.success("保存成功")

            with tab3:
                # 人员管理
                u_df = load_data("Users", ["uid", "name", "pwd", "role"])
                ed_u = st.data_editor(u_df, num_rows="dynamic")
                if st.button("💾 保存人员"):
                    # 自动生成UID
                    for i in range(len(ed_u)):
                        if not ed_u.iloc[i]["uid"]: ed_u.at[i, "uid"] = f"u_{str(uuid.uuid4())[:6]}"
                    save_data("Users", ed_u)
                    st.success("已更新")
                    st.rerun()
        else:
            # 员工看板
            st.subheader("我的待办")
            my_tasks = tasks_df[tasks_df["user"] == user["name"]]
            if not my_tasks.empty:
                st.dataframe(my_tasks)
            else:
                st.info("暂无任务")

    # --- 自定义表格 (你最想要的功能) ---
    elif selected_page.startswith("📊"):
        tab_name = selected_page.replace("📊 ", "")
        st.title(f"📊 {tab_name}")
        
        # 读取表格数据
        df = load_data(tab_name)
        
        # --- Boss 专属：修改列结构 & 权限 ---
        if is_admin:
            with st.expander(f"⚙️ 设置【{tab_name}】的结构与权限"):
                t1, t2 = st.tabs(["📝 修改列 (表头)", "🔒 设置可见人员"])
                
                with t1:
                    st.write(f"当前列: {list(df.columns)}")
                    c1, c2 = st.columns([3, 1])
                    new_col = c1.text_input("添加新列名 (例如: 采购价)")
                    if c2.button("添加列"):
                        if new_col and new_col not in df.columns:
                            # 核心修复：直接给 DataFrame 加列并保存到 Google
                            df[new_col] = "" 
                            save_data(tab_name, df)
                            st.success(f"已添加列：{new_col}")
                            st.rerun()
                    
                    # 删除列
                    del_col = st.selectbox("删除列", ["(不删除)"] + list(df.columns))
                    if del_col != "(不删除)" and st.button("确认删除"):
                        df = df.drop(columns=[del_col])
                        save_data(tab_name, df)
                        st.success("已删除")
                        st.rerun()

                with t2:
                    # 权限设置
                    all_users = load_data("Users", ["uid", "name"])
                    staff_list = all_users[all_users["role"] != "admin"]
                    
                    # 读取当前权限
                    perms = get_permissions()
                    current_allowed = perms.get(tab_name, [])
                    
                    selected_uids = st.multiselect(
                        "谁可以看这张表？",
                        options=staff_list["uid"].tolist(),
                        default=[u for u in current_allowed if u in staff_list["uid"].tolist()],
                        format_func=lambda x: staff_list[staff_list["uid"]==x]["name"].values[0]
                    )
                    
                    if st.button("💾 保存权限"):
                        save_permissions(tab_name, selected_uids)
                        st.success("权限已更新")

        # --- 数据编辑区 ---
        # 只有当表有列的时候才显示编辑器
        if not df.empty and len(df.columns) > 0:
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"editor_{tab_name}")
            
            if st.button("💾 保存表格数据", type="primary"):
                save_data(tab_name, edited_df)
                st.success("已同步到 Google Drive！")
        else:
            st.info("这张表还是空的，请在上方【设置】里添加列名（表头）。")
            
        # 删除表格按钮
        if is_admin:
            st.divider()
            if st.button("🗑️ 删除此表格"):
                sh = get_db_connection()
                ws = sh.worksheet(tab_name)
                sh.del_worksheet(ws)
                st.success("表格已删除")
                st.rerun()
