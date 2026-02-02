import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import time
import io

# ================= 1. 核心引擎 =================
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Team_Data_Center" 

# 获取北京时间 (UTC+8)
def get_beijing_time():
    utc_now = datetime.utcnow()
    beijing_now = utc_now + timedelta(hours=8)
    return beijing_now.strftime("%Y-%m-%d"), beijing_now.strftime("%H:%M")

@st.cache_resource
def get_db_connection():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"❌ 连接谷歌服务器失败: {e}")
        return None

@st.cache_data(ttl=5)
def load_data(tab_name, default_cols=[]):
    sh = get_db_connection()
    if not sh: return pd.DataFrame(columns=default_cols)
    try:
        worksheet = sh.worksheet(tab_name)
        raw_data = worksheet.get_all_values()
        if not raw_data: return pd.DataFrame(columns=default_cols)
        
        headers = raw_data[0]
        rows = raw_data[1:]
        if rows:
            df = pd.DataFrame(rows, columns=headers)
        else:
            df = pd.DataFrame(columns=headers)
            
        for col in default_cols:
            if col not in df.columns:
                df[col] = ""
        return df.astype(str)
    except:
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
             clean_df = df.astype(str)
             worksheet.update([clean_df.columns.values.tolist()] + clean_df.values.tolist())
        load_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ 保存失败: {e}")
        return False

# 辅助：数字转换
def try_float(x):
    try:
        return float(str(x).replace('¥','').replace('$','').replace(',','').strip())
    except:
        return 0.0

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
query_params = st.query_params
url_token = query_params.get("token", None)

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in and url_token:
    users_df = load_data("Users", ["uid", "name", "pwd", "role"])
    if not users_df.empty:
        user_row = users_df[users_df["uid"] == url_token]
        if not user_row.empty:
            st.session_state.logged_in = True
            st.session_state.user_info = user_row.iloc[0].to_dict()
            st.toast(f"👋 欢迎回来, {st.session_state.user_info['name']}")

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
        remember_me = st.checkbox("✅ 记住我 (免下次登录)")
        
        if st.button("登录系统", type="primary"):
            if not users_df.empty:
                user_row = users_df[users_df["name"] == selected_name].iloc[0]
                if str(user_row["pwd"]) == pwd:
                    st.session_state.logged_in = True
                    st.session_state.user_info = user_row.to_dict()
                    if remember_me:
                        st.query_params["token"] = user_row["uid"]
                    st.rerun()
                else:
                    st.error("❌ 密码错误")
            else:
                if selected_name == "Boss" and pwd == "666":
                    st.session_state.logged_in = True
                    st.session_state.user_info = DEFAULT_USERS[0]
                    st.rerun()

else:
    # ================= 4. 主界面 =================
    user = st.session_state.user_info
    is_admin = (user["role"] == "admin")
    
    # 获取北京日期
    bj_date, bj_time = get_beijing_time()
    
    with st.sidebar:
        st.info(f"👤 {user['name']}")
        st.caption(f"🕒 北京时间: {bj_time}")
        
        pages = ["📦 任务管理"]
        
        sh = get_db_connection()
        if sh:
            all_tabs = [ws.title for ws in sh.worksheets()]
            system_tabs = ["Users", "Tasks", "Assignments", "Permissions", "Settings"]
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
        
        selected_page = st.radio("系统导航", pages)
        
        st.divider()
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.query_params.clear()
            st.rerun()

    # --- 模块: 任务管理 ---
    if selected_page == "📦 任务管理":
        st.subheader("📋 任务中心")
        tasks_df = load_data("Tasks", ["date", "store", "user", "task", "status", "time"])
        assign_df = load_data("Assignments", ["store", "uid", "tasks"])
        
        # 准备人员名单
        users_df = load_data("Users", ["uid", "name"])
        name_list_all = users_df["name"].tolist()
        
        if is_admin:
            c1, c2 = st.columns([3, 1])
            with c1:
                if st.button("⚡ 一键生成今日任务 (固定)", type="primary"):
                    new_rows = []
                    for _, row in assign_df.iterrows():
                        u_name_s = users_df[users_df["uid"] == row["uid"]]["name"]
                        if not u_name_s.empty:
                            lines = [t.strip() for t in str(row["tasks"]).split('\n') if t.strip()]
                            for l in lines:
                                new_rows.append({"date": bj_date, "store": row["store"], "user": u_name_s.values[0], "task": l, "status": "进行中", "time": "-"})
                    if new_rows:
                        save_data("Tasks", pd.concat([tasks_df, pd.DataFrame(new_rows)], ignore_index=True))
                        st.success("发布成功")
                        st.rerun()
            with c2:
                 if st.button("🗑️ 清空任务"):
                     save_data("Tasks", pd.DataFrame(columns=tasks_df.columns))
                     st.rerun()

            # ⭐⭐⭐ 修复：临时任务发布窗口 ⭐⭐⭐
            with st.expander("➕ 发布临时任务 (单条)", expanded=False):
                c_t1, c_t2, c_t3 = st.columns([1, 1, 2])
                with c_t1: t_store = st.text_input("店铺名称 (如 Temu)", value="通用")
                with c_t2: t_user = st.selectbox("指派给", name_list_all)
                with c_t3: t_content = st.text_input("任务内容")
                
                if st.button("发布这条临时任务"):
                    if t_content:
                        new_row = {"date": bj_date, "store": t_store, "user": t_user, "task": t_content, "status": "进行中", "time": "-"}
                        save_data("Tasks", pd.concat([tasks_df, pd.DataFrame([new_row])], ignore_index=True))
                        st.success("已发布")
                        st.rerun()
                    else:
                        st.warning("请填写任务内容")

            # ⭐⭐⭐ 修复：表格显示汉化 (使用 column_config) ⭐⭐⭐
            st.dataframe(
                tasks_df, 
                use_container_width=True,
                column_config={
                    "date": "日期",
                    "store": "店铺",
                    "user": "负责人",
                    "task": "任务内容",
                    "status": "状态",
                    "time": "完成时间"
                }
            )
            
            with st.expander("🔗 设置岗位分配 (固定日常任务)"):
                users_df = load_data("Users", ["uid", "name"])
                uid_map = dict(zip(users_df["uid"], users_df["name"]))
                name_map = dict(zip(users_df["name"], users_df["uid"]))
                
                assign_display = assign_df.copy()
                if not assign_display.empty and "uid" in assign_display.columns:
                     assign_display["员工"] = assign_display["uid"].map(uid_map).fillna("未知")
                     assign_display = assign_display.drop(columns=["uid"], errors='ignore')
                else:
                    assign_display["员工"] = ""
                
                edited_assign = st.data_editor(
                    assign_display, 
                    column_config={
                        "员工": st.column_config.SelectboxColumn("员工", options=users_df["name"].tolist(), required=True),
                        "store": st.column_config.TextColumn("店铺"),
                        "tasks": st.column_config.TextColumn("任务内容 (换行区分多条)")
                    },
                    num_rows="dynamic", 
                    use_container_width=True
                )
                
                if st.button("💾 保存分配"):
                    save_rows = []
                    for idx, row in edited_assign.iterrows():
                        if row["员工"] and row["员工"] in name_map:
                            save_rows.append({"store": row["store"],"uid": name_map[row["员工"]],"tasks": row["tasks"]})
                    save_data("Assignments", pd.DataFrame(save_rows))
                    st.success("保存成功")
            
            with st.expander("👥 人员名单管理"):
                 u_df = load_data("Users", ["uid", "name", "pwd", "role"])
                 # ⭐⭐⭐ 修复：人员表汉化 ⭐⭐⭐
                 ed_u = st.data_editor(
                     u_df, 
                     num_rows="dynamic",
                     column_config={
                         "uid": st.column_config.TextColumn("用户ID (自动生成)", disabled=True),
                         "name": "姓名",
                         "pwd": "密码",
                         "role": st.column_config.SelectboxColumn("角色", options=["admin", "staff"])
                     }
                 )
                 if st.button("💾 保存人员"):
                    for i in range(len(ed_u)):
                        if not ed_u.iloc[i]["uid"]: ed_u.at[i, "uid"] = f"u_{str(uuid.uuid4())[:6]}"
                    save_data("Users", ed_u)
                    st.success("人员已更新")
                    st.rerun()

        else:
            # 员工端
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
                                # ⭐⭐⭐ 修复：使用北京时间打卡 ⭐⭐⭐
                                tasks_df.at[idx, "time"] = bj_time
                                save_data("Tasks", tasks_df)
                                st.rerun()
                        else:
                            c3.success(f"已完成 {row['time']}")
            else:
                st.info("暂无任务")

    # --- 模块: 自定义表格 (保持完美状态) ---
    elif selected_page.startswith("📊"):
        tab_name = selected_page.replace("📊 ", "")
        st.subheader(f"📝 {tab_name}")
        
        df = load_data(tab_name)
        
        if is_admin:
            with st.expander(f"🔒 设置谁能看【{tab_name}】"):
                all_users = load_data("Users", ["uid", "name"])
                staffs = all_users[all_users["role"] != "admin"]
                perms = get_permissions()
                curr = perms.get(tab_name, [])
                
                sel_uids = st.multiselect(
                    "勾选允许查看的员工 (老板默认可见)",
                    options=staffs["uid"].tolist(),
                    default=[u for u in curr if u in staffs["uid"].tolist()],
                    format_func=lambda x: staffs[staffs["uid"]==x]["name"].values[0]
                )
                if st.button("💾 更新查看权限"):
                    save_permissions(tab_name, sel_uids)
                    st.success("权限已保存！")

        with st.expander("🧮 表格超级计算器 (支持函数公式)"):
            st.info("💡 使用 Python 语法计算。例如：计算人民币利润，可以输入 `(售价 * 7.2) - 成本`")
            c_cal1, c_cal2 = st.columns([3, 1])
            with c_cal1:
                cols_str = "、".join([f"`{c}`" for c in df.columns])
                st.caption(f"当前可用列名：{cols_str}")
                formula = st.text_input("输入计算公式", placeholder="例如: 售价 * 7.2 - 成本")
                new_col_name = st.text_input("计算结果存入列名", value="计算结果")
                
            with c_cal2:
                st.write("") 
                st.write("") 
                if st.button("🚀 执行计算"):
                    if not formula:
                        st.warning("请输入公式")
                    else:
                        try:
                            temp_df = df.copy()
                            for col in df.columns:
                                temp_df[col] = temp_df[col].apply(try_float)
                            result = temp_df.eval(formula)
                            df[new_col_name] = result.round(2).astype(str)
                            save_data(tab_name, df)
                            st.success(f"计算完成！结果已存入【{new_col_name}】")
                            st.rerun()
                        except Exception as e:
                            st.error(f"公式错误: {e}。请检查列名是否写对。")

        if not df.empty and len(df.columns) > 0:
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"editor_{tab_name}")
            c_save, c_del = st.columns([4, 1])
            with c_save:
                if st.button("💾 保存表格数据", type="primary"):
                    save_data(tab_name, edited_df)
                    st.success("✅ 已同步到 Google 云端")
            
            if is_admin:
                with c_del:
                    with st.popover("🗑️ 删除此表"):
                        st.write("数据删除后无法恢复！")
                        if st.button("🔴 确认彻底删除"):
                             sh = get_db_connection()
                             sh.del_worksheet(sh.worksheet(tab_name))
                             load_data.clear()
                             st.rerun()
        else:
            st.info("这是一个空表，请使用下方的导入功能。")

        if is_admin:
            st.divider()
            with st.expander("📤 导入/覆盖数据 (Excel/CSV)"):
                st.warning("⚠️ 注意：导入将直接覆盖上方当前表格的所有内容。")
                uploaded_file = st.file_uploader("选择文件", type=['xlsx', 'csv'])
                if uploaded_file is not None:
                    if st.button("🚀 确认导入并覆盖"):
                        try:
                            if uploaded_file.name.endswith('.csv'): import_df = pd.read_csv(uploaded_file)
                            else: import_df = pd.read_excel(uploaded_file)
                            if save_data(tab_name, import_df.astype(str)):
                                st.success("导入成功！页面即将刷新...")
                                time.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"导入失败: {e} (请检查 requirements.txt)")

    if is_admin:
        with st.sidebar:
            st.divider()
            with st.expander("➕ 创建新表格"):
                new_name = st.text_input("新表格名称")
                if st.button("创建"):
                    if new_name and new_name not in all_tabs:
                        df_init = pd.DataFrame(columns=["A"]) 
                        save_data(new_name, df_init)
                        st.toast("✅ 创建成功！请前往导入数据。")
                        time.sleep(1)
                        st.rerun()
                    elif new_name in all_tabs:
                        st.error("表格名字重复了")
