import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import time
import io

# ================= 1. 核心引擎 =================
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Team_Data_Center" 

@st.cache_resource
def get_db_connection():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"❌ 连接失败: {e}")
        return None

# ⭐ 核心修复：使用 get_all_values 确保即使没数据也能读到表头
@st.cache_data(ttl=5)
def load_data(tab_name, default_cols=[]):
    sh = get_db_connection()
    if not sh: return pd.DataFrame(columns=default_cols)
    try:
        worksheet = sh.worksheet(tab_name)
        # 改用 get_all_values 读取原始数据（包含表头）
        raw_data = worksheet.get_all_values()
        
        if not raw_data:
            # 真正的空表
            return pd.DataFrame(columns=default_cols)
            
        headers = raw_data[0] # 第一行是表头
        rows = raw_data[1:]   # 后面是数据
        
        # 如果有数据
        if rows:
            df = pd.DataFrame(rows, columns=headers)
        else:
            # 只有表头，没有数据
            df = pd.DataFrame(columns=headers)
            
        # 补全缺失列
        for col in default_cols:
            if col not in df.columns:
                df[col] = ""
        return df.astype(str)
        
    except gspread.WorksheetNotFound:
        return pd.DataFrame(columns=default_cols)
    except Exception as e:
        return pd.DataFrame(columns=default_cols)

def save_data(tab_name, df):
    sh = get_db_connection()
    if not sh: return False
    try:
        try:
            worksheet = sh.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=tab_name, rows=100, cols=20)
        
        worksheet.clear()
        # 写入 DataFrame (含表头)
        if df.empty:
             worksheet.update([df.columns.values.tolist()])
        else:
             # 将所有数据转为字符串写入，防止格式错误
             clean_df = df.astype(str)
             worksheet.update([clean_df.columns.values.tolist()] + clean_df.values.tolist())
             
        load_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ 保存失败: {e}")
        return False

# 读取模板设置
def get_template_cols():
    df = load_data("System_Template", ["列名"])
    if df.empty:
        return ["货号", "产品名称", "图片链接", "成本", "售价", "供应商", "备注"]
    return df["列名"].tolist()

# 权限管理
def get_permissions():
    df = load_data("Permissions", ["table_name", "allowed_uids"])
    perms = {}
    if not df.empty:
        for _, row in df.iterrows():
            perms[row["table_name"]] = str(row["allowed_uids"]).split(",")
    return perms

def save_permissions(table_name, uid_list):
    df = load_data("Permissions", ["table_name", "allowed_uids"])
    df = df[df["table_name"] != table_name]
    new_row = {"table_name": table_name, "allowed_uids": ",".join(uid_list)}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_data("Permissions", df)

# ================= 2. 初始配置 =================
DEFAULT_USERS = [{"uid": "u_boss", "name": "Boss", "pwd": "666", "role": "admin"}]

st.set_page_config(page_title="Boss系统", layout="wide")

# ================= 3. 登录逻辑 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🚀 团队协作系统")
    users_df = load_data("Users", ["uid", "name", "pwd", "role"])
    
    if users_df.empty:
        users_df = pd.DataFrame(DEFAULT_USERS)
        save_data("Users", users_df)
    
    name_list = users_df["name"].tolist() if not users_df.empty else ["Boss"]
    
    c1, c2 = st.columns([2,1])
    with c1:
        selected_name = st.selectbox("账号", name_list)
        pwd = st.text_input("密码", type="password")
        if st.button("登录", type="primary"):
            if not users_df.empty:
                user_row = users_df[users_df["name"] == selected_name].iloc[0]
                if str(user_row["pwd"]) == pwd:
                    st.session_state.logged_in = True
                    st.session_state.user_info = user_row.to_dict()
                    st.rerun()
                else:
                    st.error("密码错误")
            else:
                if selected_name == "Boss" and pwd == "666":
                    st.session_state.logged_in = True
                    st.session_state.user_info = DEFAULT_USERS[0]
                    st.rerun()

else:
    # ================= 4. 主界面 =================
    user = st.session_state.user_info
    is_admin = (user["role"] == "admin")
    
    with st.sidebar:
        st.info(f"👤 {user['name']}")
        
        pages = ["📦 任务管理"]
        
        sh = get_db_connection()
        if sh:
            all_tabs = [ws.title for ws in sh.worksheets()]
            system_tabs = ["Users", "Tasks", "Assignments", "Permissions", "Settings", "System_Template"]
            custom_tabs = [t for t in all_tabs if t not in system_tabs]
            
            perms = get_permissions()
            visible_tabs = []
            for t in custom_tabs:
                allowed = perms.get(t, [])
                if is_admin or (user["uid"] in allowed):
                    visible_tabs.append(t)
            
            if visible_tabs:
                st.divider()
                st.caption("我的数据表")
                for t in visible_tabs:
                    pages.append(f"📊 {t}")
        else:
            all_tabs = []
            
        if is_admin:
            st.divider()
            pages.append("⚙️ 全局系统设置")
        
        selected_page = st.radio("导航", pages)
        
        st.divider()
        if st.button("退出"):
            st.session_state.logged_in = False
            st.rerun()

    # --- 模块 A: 全局设置 ---
    if selected_page == "⚙️ 全局系统设置":
        st.header("⚙️ 全局系统设置")
        t1, t2 = st.tabs(["📝 表格默认模板", "👥 人员管理"])
        with t1:
            st.caption("修改这里，以后【新建表格】都会默认带上这些列：")
            current_cols = get_template_cols()
            df_tpl = pd.DataFrame({"列名": current_cols})
            edited_tpl = st.data_editor(df_tpl, num_rows="dynamic", use_container_width=True)
            if st.button("💾 保存模板"):
                new_col_list = [r["列名"] for r in edited_tpl.to_dict('records') if r["列名"]]
                save_data("System_Template", pd.DataFrame({"列名": new_col_list}))
                st.success("模板已更新")
        with t2:
            u_df = load_data("Users", ["uid", "name", "pwd", "role"])
            ed_u = st.data_editor(u_df, num_rows="dynamic")
            if st.button("💾 保存人员"):
                for i in range(len(ed_u)):
                    if not ed_u.iloc[i]["uid"]: ed_u.at[i, "uid"] = f"u_{str(uuid.uuid4())[:6]}"
                save_data("Users", ed_u)
                st.success("人员已更新")
                st.rerun()

    # --- 模块 B: 任务管理 ---
    elif selected_page == "📦 任务管理":
        st.subheader("📋 任务中心")
        tasks_df = load_data("Tasks", ["date", "store", "user", "task", "status", "time"])
        assign_df = load_data("Assignments", ["store", "uid", "tasks"])
        
        if is_admin:
            c1, c2 = st.columns([3, 1])
            with c1:
                if st.button("⚡ 生成今日任务", type="primary"):
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
                        st.success("发布成功")
                        st.rerun()
            with c2:
                 if st.button("🗑️ 清空任务"):
                     save_data("Tasks", pd.DataFrame(columns=tasks_df.columns))
                     st.rerun()

            st.dataframe(tasks_df, use_container_width=True)
            with st.expander("🔗 设置岗位分配"):
                edited_assign = st.data_editor(assign_df, num_rows="dynamic", use_container_width=True)
                if st.button("💾 保存分配"):
                    save_data("Assignments", edited_assign)
                    st.success("保存成功")
        else:
            my_tasks = tasks_df[tasks_df["user"] == user["name"]]
            if not my_tasks.empty:
                for idx, row in my_tasks.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 5, 2])
                        c1.markdown(f"**{row['store']}**")
                        c2.write(row['task'])
                        if row['status'] == "进行中":
                            if c3.button("✅ 打卡", key=f"dka_{idx}"):
                                tasks_df.at[idx, "status"] = "完成"
                                tasks_df.at[idx, "time"] = datetime.now().strftime("%H:%M")
                                save_data("Tasks", tasks_df)
                                st.rerun()
                        else:
                            c3.success(f"已完成 {row['time']}")
            else:
                st.info("暂无任务")

    # --- 模块 C: 自定义表格 (含导入功能) ---
    elif selected_page.startswith("📊"):
        tab_name = selected_page.replace("📊 ", "")
        st.subheader(f"📝 {tab_name}")
        
        df = load_data(tab_name)
        
        # ⭐⭐⭐ 新增：Excel 导入区 ⭐⭐⭐
        if is_admin:
            with st.expander("📤 导入 Excel / CSV 数据 (点击展开)"):
                st.caption("提示：上传的文件将直接覆盖当前表格内容，请确保第一行是列名。")
                uploaded_file = st.file_uploader("选择文件", type=['xlsx', 'csv'])
                if uploaded_file is not None:
                    if st.button("🚀 确认导入并覆盖"):
                        try:
                            if uploaded_file.name.endswith('.csv'):
                                import_df = pd.read_csv(uploaded_file)
                            else:
                                import_df = pd.read_excel(uploaded_file)
                            
                            # 强制转为字符，防止兼容性问题
                            import_df = import_df.astype(str)
                            
                            if save_data(tab_name, import_df):
                                st.success(f"成功导入 {len(import_df)} 行数据！")
                                st.rerun()
                        except Exception as e:
                            st.error(f"导入失败: {e}。请确保 Requirements.txt 里加了 openpyxl")

        # 数据编辑区
        # 修复逻辑：只要 df 不是 None，就显示编辑器，哪怕是空表也能看见列头
        edited_df = st.data_editor(
            df, 
            num_rows="dynamic", 
            use_container_width=True,
            key=f"editor_{tab_name}"
        )
        
        c1, c2 = st.columns([4, 1])
        with c1:
            if st.button("💾 保存表格数据", type="primary"):
                save_data(tab_name, edited_df)
                st.success("已同步到 Google 云端")
        
        if is_admin:
            with c2:
                with st.popover("🗑️ 删除"):
                    st.write("确定删除吗？")
                    if st.button("确认删除"):
                        sh = get_db_connection()
                        ws = sh.worksheet(tab_name)
                        sh.del_worksheet(ws)
                        load_data.clear()
                        st.rerun()

    # --- 侧边栏底部：新建表格 ---
    if is_admin and selected_page != "⚙️ 全局系统设置":
        with st.sidebar:
            st.divider()
            with st.expander("➕ 新建 Excel 表格"):
                new_name = st.text_input("表名")
                if st.button("创建"):
                    if new_name and new_name not in all_tabs:
                        tpl_cols = get_template_cols()
                        df_init = pd.DataFrame(columns=tpl_cols)
                        save_data(new_name, df_init)
                        st.toast("创建成功！")
                        time.sleep(1)
                        st.rerun()
