import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
import uuid

# ================= 1. 核心配置 =================
CONFIG_FILE = "config_v7.json"
TASK_DB = "tasks.csv"
# 这里的 TABLES_FILE 是一个“大仓库”，里面存放你所有的自定义表格数据
TABLES_FILE = "custom_tables.json" 

# 默认配置
DEFAULT_CONFIG = {
    "users": {
        "u_boss": {"name": "Boss", "pwd": "666", "role": "admin"},
        "u_001": {"name": "小王", "pwd": "111", "role": "staff"},
        "u_002": {"name": "小李", "pwd": "222", "role": "staff"}
    },
    "stores": ["TikTok店铺-01", "TikTok店铺-02", "TikTok店铺-03", "TikTok店铺-04"],
    "assignments": []
}

# --- 加载与保存函数 ---
def load_json(filepath, default=None):
    if not os.path.exists(filepath):
        return default if default is not None else {}
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def save_json(filepath, data):
    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_name_by_id(config, uid):
    return config["users"].get(uid, {}).get("name", "❌已删除")

def get_id_by_name(config, name):
    for uid, info in config["users"].items():
        if info["name"] == name: return uid
    return None

# 加载数据
config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
# 加载自定义表格库 (结构: {"表名": {"data": [行数据], "users": [允许看的人UID]}})
tables_db = load_json(TABLES_FILE, {})

if not os.path.exists(TASK_DB):
    pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(TASK_DB, index=False)

st.set_page_config(page_title="吴先生团队超级系统", layout="wide")

# ================= 2. 登录系统 =================
query_params = st.query_params
url_token = query_params.get("token", None)

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_uid = None

if not st.session_state.logged_in and url_token:
    if url_token in config["users"]:
        st.session_state.logged_in = True
        st.session_state.user_uid = url_token
        st.toast(f"欢迎回来，{config['users'][url_token]['name']}")

if not st.session_state.logged_in:
    st.title("🚀 团队任务管理系统")
    user_names = [info["name"] for uid, info in config["users"].items()]
    selected_name = st.selectbox("选择角色", user_names)
    pwd = st.text_input("密码", type="password")
    remember_me = st.checkbox("✅ 记住我 (刷新免登录)")
    if st.button("登录", type="primary"):
        uid = get_id_by_name(config, selected_name)
        if uid and config["users"][uid]["pwd"] == pwd:
            st.session_state.logged_in = True
            st.session_state.user_uid = uid
            if remember_me: st.query_params["token"] = uid
            st.rerun()
        else:
            st.error("密码错误")

else:
    # ================= 3. 主界面 =================
    current_uid = st.session_state.user_uid
    if current_uid not in config["users"]:
        st.session_state.logged_in = False
        st.query_params.clear()
        st.rerun()

    current_user_info = config["users"][current_uid]
    current_name = current_user_info["name"]
    is_admin = (current_user_info.get("role") == "admin")

    # --- 左侧菜单 ---
    with st.sidebar:
        st.title(f"👋 {current_name}")
        
        # 任何人都能看任务，但“多平台表格库”需要有权限的表才会显示
        selected_page = st.radio("切换系统：", ["📦 任务管理", "📊 多平台数据表格库"])
        
        st.divider()
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.session_state.user_uid = None
            st.query_params.clear()
            st.rerun()

    # ================= 页面 A: 任务管理 (保持原样) =================
    if selected_page == "📦 任务管理":
        try:
            df = pd.read_csv(TASK_DB)
        except:
            df = pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"])

        if is_admin:
            st.title("📊 任务控制台")
            tab1, tab2, tab3 = st.tabs(["⚡ 每日派单", "🔗 岗位分配", "⚙️ 基础设置"])
            
            with tab1:
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.button("⚡ 生成今日任务", type="primary"):
                        today = datetime.now().strftime("%Y-%m-%d")
                        new_rows = []
                        count = 0
                        for item in config.get("assignments", []):
                            if item["store"] not in config["stores"]: continue
                            assigned_uid = item["uid"]
                            if assigned_uid in config["users"]:
                                real_name = config["users"][assigned_uid]["name"]
                                task_lines = [t.strip() for t in item.get("tasks", "").split('\n') if t.strip()]
                                for t in task_lines:
                                    new_rows.append({"日期": today, "店铺": item["store"], "负责人": real_name, "任务内容": t, "状态": "进行中", "完成时间": "-"})
                                    count += 1
                        if new_rows:
                            new_df = pd.DataFrame(new_rows)
                            df = pd.concat([df, new_df], ignore_index=True)
                            df.to_csv(TASK_DB, index=False)
                            st.success(f"已生成 {count} 条任务！")
                            st.rerun()
                with col2:
                     if st.button("🗑️ 清空历史"):
                         pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(TASK_DB, index=False)
                         st.rerun()
                st.dataframe(df, use_container_width=True)

            with tab2:
                st.subheader("🔗 岗位分配")
                display_data = []
                for item in config.get("assignments", []):
                    uid = item["uid"]
                    name = get_name_by_id(config, uid)
                    display_data.append({"店铺": item["store"], "员工": name, "指令": item["tasks"]})
                
                df_edit = pd.DataFrame(display_data)
                if df_edit.empty: df_edit = pd.DataFrame(columns=["店铺", "员工", "指令"])

                edited_df = st.data_editor(
                    df_edit,
                    column_config={
                        "店铺": st.column_config.SelectboxColumn(options=config["stores"], required=True),
                        "员工": st.column_config.SelectboxColumn(options=[u["name"] for k,u in config["users"].items() if u["role"]!="admin"], required=True),
                        "指令": st.column_config.TextColumn(width="large")
                    },
                    num_rows="dynamic",
                    use_container_width=True
                )
                if st.button("💾 保存分配"):
                    new_assignments = []
                    for index, row in edited_df.iterrows():
                        if row["店铺"] and row["员工"]:
                            found_uid = get_id_by_name(config, row["员工"])
                            if found_uid:
                                new_assignments.append({"store": row["店铺"], "uid": found_uid, "tasks": row["指令"]})
                    config["assignments"] = new_assignments
                    save_config(config, CONFIG_FILE) # 修正保存路径
                    st.success("分配已保存！")

            with tab3:
                st.subheader("⚙️ 资源管理")
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**人员管理**")
                    users_list = []
                    for uid, info in config["users"].items():
                        users_list.append({"ID": uid, "姓名": info["name"], "密码": info["pwd"], "角色": info["role"]})
                    edited_users = st.data_editor(
                        pd.DataFrame(users_list),
                        column_config={"ID": st.column_config.TextColumn(disabled=True), "角色": st.column_config.SelectboxColumn(options=["admin", "staff"])},
                        num_rows="dynamic"
                    )
                    if st.button("💾 保存人员"):
                        new_users_dict = {}
                        for index, row in edited_users.iterrows():
                            uid = row["ID"]
                            if not uid or pd.isna(uid): uid = f"u_{str(uuid.uuid4())[:8]}"
                            new_users_dict[uid] = {"name": row["姓名"], "pwd": str(row["密码"]), "role": row["角色"]}
                        config["users"] = new_users_dict
                        save_config(config, CONFIG_FILE)
                        st.success("人员已更新")
                        st.rerun()
                
                with c2:
                    st.write("**店铺管理**")
                    stores_df = pd.DataFrame(config["stores"], columns=["店铺名称"])
                    edited_stores = st.data_editor(stores_df, num_rows="dynamic")
                    if st.button("💾 保存店铺"):
                        config["stores"] = [s for s in edited_stores["店铺名称"] if s]
                        save_config(config, CONFIG_FILE)
                        st.success("店铺已更新")

        else: # 员工视图
            st.title(f"📋 {current_name} 的待办")
            my_tasks = df[df["负责人"] == current_name]
            if my_tasks.empty:
                st.info("今日暂无任务")
            else:
                for index, row in my_tasks.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 5, 3])
                        c1.markdown(f"**{row['店铺']}**")
                        c2.markdown(f"{row['任务内容']}")
                        if row['状态'] == "进行中":
                            if c3.button("打卡", key=f"btn_{index}"):
                                df.at[index, "状态"] = "✅ 已完成"
                                df.at[index, "完成时间"] = datetime.now().strftime("%H:%M:%S")
                                df.to_csv(TASK_DB, index=False)
                                st.rerun()
                        else:
                            c3.write(f"已完成 {row['完成时间']}")

    # ================= 页面 B: 📊 多平台数据表格库 (全新逻辑) =================
    elif selected_page == "📊 多平台数据表格库":
        st.title("📊 多平台自定义数据库")
        st.caption("在这里，你可以创建任意结构的表格，并指定谁有权查看。")
        
        # 1. 筛选出“我”能看到的表 (Boss看所有，员工看授权)
        allowed_tables = []
        for table_name, table_info in tables_db.items():
            # 权限检查：如果是Boss 或者 自己的ID在白名单里
            authorized_users = table_info.get("users", [])
            if is_admin or (current_uid in authorized_users):
                allowed_tables.append(table_name)
        
        # --- 管理员功能：创建新表 ---
        if is_admin:
            with st.expander("➕ 创建新表格 (仅老板可见)"):
                c1, c2 = st.columns([3, 1])
                new_table_name = c1.text_input("新表格名称 (例如: Temu成本表)")
                if c2.button("创建"):
                    if new_table_name and new_table_name not in tables_db:
                        # 初始化：空数据，空列
                        tables_db[new_table_name] = {"data": [], "users": []}
                        save_json(TABLES_FILE, tables_db)
                        st.success(f"表格 {new_table_name} 创建成功！")
                        st.rerun()
                    elif new_table_name in tables_db:
                        st.error("表格名已存在")

        # --- 选择要操作的表格 ---
        if not allowed_tables:
            st.info("暂无可见表格，请联系老板创建。")
        else:
            selected_table = st.selectbox("选择表格：", allowed_tables)
            
            # 获取当前表格的数据
            current_table_data = tables_db[selected_table].get("data", [])
            current_table_users = tables_db[selected_table].get("users", [])
            
            # 转为 DataFrame
            df_custom = pd.DataFrame(current_table_data)

            # --- 表结构修改 (仅老板) ---
            if is_admin:
                with st.expander(f"⚙️ 设置【{selected_table}】的列与权限"):
                    t1, t2 = st.tabs(["📝 修改列 (表头)", "🔒 设置可见人员"])
                    
                    with t1:
                        st.write("目前列名:", list(df_custom.columns))
                        col_c1, col_c2 = st.columns([3, 1])
                        new_col = col_c1.text_input("添加新列名 (例如: 采购价)")
                        if col_c2.button("添加列"):
                            if new_col and new_col not in df_custom.columns:
                                df_custom[new_col] = "" # 给所有行添加这个新列
                                # 保存
                                tables_db[selected_table]["data"] = df_custom.to_dict('records')
                                save_json(TABLES_FILE, tables_db)
                                st.success(f"列 {new_col} 已添加")
                                st.rerun()
                        
                        # 删除列
                        del_col = st.selectbox("选择要删除的列", ["(不删除)"] + list(df_custom.columns))
                        if del_col != "(不删除)" and st.button("⚠️ 确认删除该列"):
                            df_custom = df_custom.drop(columns=[del_col])
                            tables_db[selected_table]["data"] = df_custom.to_dict('records')
                            save_json(TABLES_FILE, tables_db)
                            st.success(f"列 {del_col} 已删除")
                            st.rerun()

                    with t2:
                        all_staff = [u for u in config["users"] if config["users"][u]["role"] != "admin"]
                        # 转换 UID 为名字显示
                        selected_staff = st.multiselect(
                            "谁可以看这个表？(Boss默认可见)",
                            options=all_staff,
                            default=[u for u in current_table_users if u in all_staff],
                            format_func=lambda x: config["users"][x]["name"]
                        )
                        if st.button("💾 保存表格权限"):
                            tables_db[selected_table]["users"] = selected_staff
                            save_json(TABLES_FILE, tables_db)
                            st.success("权限已更新！")

                # 删除表格按钮
                if st.button(f"🗑️ 删除整个表格【{selected_table}】", type="secondary"):
                    del tables_db[selected_table]
                    save_json(TABLES_FILE, tables_db)
                    st.success("表格已删除")
                    st.rerun()

            st.divider()
            
            # --- 核心：自由编辑区域 ---
            st.subheader(f"📝 {selected_table}")
            
            # 只有当有列的时候，才能编辑。如果没有列，提示老板先加列。
            if df_custom.empty and len(df_custom.columns) == 0:
                st.warning("这张表还没有任何列（表头）。请老板在上方【设置】里添加列名，比如“产品名”、“成本”等。")
            else:
                edited_df = st.data_editor(
                    df_custom,
                    num_rows="dynamic",
                    use_container_width=True,
                    key=f"editor_{selected_table}"
                )
                
                if st.button("💾 保存数据", type="primary"):
                    # 将 DataFrame 转回 json 格式保存
                    # 替换 NaN 为空字符串，防止 JSON 报错
                    cleaned_data = edited_df.fillna("").to_dict('records')
                    tables_db[selected_table]["data"] = cleaned_data
                    save_json(TABLES_FILE, tables_db)
                    st.success(f"【{selected_table}】数据已保存！")
