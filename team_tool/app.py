import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import time

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

@st.cache_data(ttl=5)
def load_data(tab_name, default_cols=[]):
    sh = get_db_connection()
    if not sh: return pd.DataFrame(columns=default_cols)
    try:
        worksheet = sh.worksheet(tab_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        for col in default_cols:
            if col not in df.columns:
                df[col] = ""
        return df.astype(str)
    except gspread.WorksheetNotFound:
        return pd.DataFrame(columns=default_cols)
    except:
        time.sleep(1)
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
        if df.empty:
            worksheet.update([df.columns.values.tolist()])
        else:
            worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        load_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ 保存失败: {e}")
        return False

# --- 新增：专门读取“表格模板”的功能 ---
def get_template_cols():
    # 尝试从 Google 读取配置表
    df = load_data("System_Template", ["列名"])
    if df.empty:
        # 如果第一次用，没有配置表，就用这套默认的
        return ["货号", "产品名称", "图片链接", "成本", "售价", "供应商", "备注"]
    return df["列名"].tolist()

def save_template_cols(col_list):
    # 把用户设置的列名保存到 Google
    df = pd.DataFrame({"列名": col_list})
    save_data("System_Template", df)

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
        
        # 自动加载表格
        sh = get_db_connection()
        if sh:
            all_tabs = [ws.title for ws in sh.worksheets()]
            # 排除系统表
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
            
        # ⭐️ 新增：全局设置入口
        if is_admin:
            st.divider()
            pages.append("⚙️ 全局系统设置")
        
        selected_page = st.radio("导航", pages)
        
        st.divider()
        if st.button("退出"):
            st.session_state.logged_in = False
            st.rerun()

    # --- 模块 A: 全局设置 (这里是你最想要的) ---
    if selected_page == "⚙️ 全局系统设置":
        st.header("⚙️ 全局系统设置")
        st.info("在这里修改配置，无需再改代码！")
        
        tab_tpl, tab_user = st.tabs(["📝 表格默认模板", "👥 人员管理"])
        
        with tab_tpl:
            st.subheader("设置新建表格的默认列")
            st.caption("以后每次【新建表格】，都会自动包含下面这些列：")
            
            # 读取当前模板
            current_cols = get_template_cols()
            # 转成 DataFrame 方便编辑
            df_tpl = pd.DataFrame({"列名": current_cols})
            
            edited_tpl = st.data_editor(
                df_tpl, 
                num_rows="dynamic", 
                use_container_width=True,
                key="tpl_editor"
            )
            
            if st.button("💾 保存模板设置"):
                # 提取列名列表
                new_col_list = [r["列名"] for r in edited_tpl.to_dict('records') if r["列名"]]
                save_template_cols(new_col_list)
                st.success("✅ 模板已更新！下次新建表格时生效。")

        with tab_user:
            st.subheader("系统人员管理")
            u_df = load_data("Users", ["uid", "name", "pwd", "role"])
            ed_u = st.data_editor(u_df, num_rows="dynamic")
            if st.button("💾 保存人员名单"):
                for i in range(len(ed_u)):
                    if not ed_u.iloc[i]["uid"]: ed_u.at[i, "uid"] = f"u_{str(uuid.uuid4())[:6]}"
                save_data("Users", ed_u)
                st.success("已更新")
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
            
            with st.expander("🔗 设置岗位分配 (谁 -> 哪个店 -> 做什么)"):
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

    # --- 模块 C: 自定义表格 (WPS模式) ---
    elif selected_page.startswith("📊"):
        tab_name = selected_page.replace("📊 ", "")
        st.subheader(f"📝 {tab_name}")
        
        df = load_data(tab_name)
        
        # 老板创建新表 (放在这里或侧边栏都可以，这里放一个入口)
        if is_admin:
            with st.expander("⚙️ 表格操作"):
                t1, t2 = st.tabs(["修改列/权限", "删除表格"])
                with t1:
                    c1, c2 = st.columns([3, 1])
                    new_col = c1.text_input("加列", key="new_col_input")
                    if c2.button("添加"):
                        if new_col and new_col not in df.columns:
                            df[new_col] = ""
                            save_data(tab_name, df)
                            st.rerun()
                    
                    # 权限
                    all_users = load_data("Users", ["uid", "name"])
                    staffs = all_users[all_users["role"] != "admin"]
                    perms = get_permissions()
                    curr = perms.get(tab_name, [])
                    sel = st.multiselect("可见人员", staffs["uid"].tolist(), default=[u for u in curr if u in staffs["uid"].tolist()], format_func=lambda x: staffs[staffs["uid"]==x]["name"].values[0])
                    if st.button("保存权限"):
                        save_permissions(tab_name, sel)
                        st.success("权限已更新")
                with t2:
                    if st.button(f"🗑️ 删除 {tab_name}"):
                         sh = get_db_connection()
                         sh.del_worksheet(sh.worksheet(tab_name))
                         load_data.clear()
                         st.rerun()

        if not df.empty and len(df.columns) > 0:
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
            if st.button("💾 保存数据", type="primary"):
                save_data(tab_name, edited_df)
                st.success("已同步到 Google 云端")
        else:
            st.warning("表格为空")

    # --- 侧边栏底部：新建表格入口 ---
    if is_admin and selected_page != "⚙️ 全局系统设置":
        with st.sidebar:
            st.divider()
            with st.expander("➕ 新建 Excel 表格"):
                new_name = st.text_input("表名")
                if st.button("创建"):
                    if new_name and new_name not in all_tabs:
                        # ⭐️ 核心：读取你在“全局设置”里填写的模板
                        tpl_cols = get_template_cols()
                        df_init = pd.DataFrame(columns=tpl_cols)
                        save_data(new_name, df_init)
                        st.toast("创建成功！")
                        time.sleep(1)
                        st.rerun()
