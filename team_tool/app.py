import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
import uuid

# ================= 1. 核心配置 =================
CONFIG_FILE = "config_v6.json"
TASK_DB = "tasks.csv"
PRODUCT_DB = "products.csv" # 新增：产品数据库

# 默认配置 (保留了你熟悉的结构)
DEFAULT_CONFIG = {
    "users": {
        "u_boss": {"name": "Boss", "pwd": "666", "role": "admin"},
        "u_001": {"name": "小王", "pwd": "111", "role": "staff"},
        "u_002": {"name": "小李", "pwd": "222", "role": "staff"}
    },
    "stores": ["TikTok店铺-01", "TikTok店铺-02", "TikTok店铺-03", "TikTok店铺-04"],
    "assignments": [], # 你的灵活分配数据存在这里
    "product_access": [] # 新增：谁能看产品库的白名单
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        config = json.load(f)
        if "product_access" not in config: config["product_access"] = []
        return config

def save_config(config):
    with open(CONFIG_FILE, "w", encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

def get_name_by_id(config, uid):
    return config["users"].get(uid, {}).get("name", "❌已删除")

def get_id_by_name(config, name):
    for uid, info in config["users"].items():
        if info["name"] == name: return uid
    return None

config = load_config()

# 初始化两个数据库
if not os.path.exists(TASK_DB):
    pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(TASK_DB, index=False)
if not os.path.exists(PRODUCT_DB):
    pd.DataFrame(columns=["货号", "产品名称", "成本价(CNY)", "售价(USD)", "供应商", "备注"]).to_csv(PRODUCT_DB, index=False)

st.set_page_config(page_title="吴先生团队系统 (集成版)", layout="wide")

# ================= 2. 登录系统 (你喜欢的记住我功能) =================
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
    # ================= 3. 主系统 (含侧边栏切换) =================
    current_uid = st.session_state.user_uid
    if current_uid not in config["users"]:
        st.session_state.logged_in = False
        st.query_params.clear()
        st.rerun()

    current_user_info = config["users"][current_uid]
    current_name = current_user_info["name"]
    is_admin = (current_user_info.get("role") == "admin")

    # --- 左侧菜单 (这就是新加的墙) ---
    with st.sidebar:
        st.title(f"👋 {current_name}")
        
        # 只有被授权的人才能看到“产品库”选项
        page_options = ["📦 任务管理"] # 每个人都能看任务
        
        # 权限判断：是老板 或者 在白名单里
        if is_admin or (current_uid in config.get("product_access", [])):
            page_options.append("💰 产品与成本库") # 新功能入口
            
        selected_page = st.radio("切换功能：", page_options)
        
        st.divider()
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.session_state.user_uid = None
            st.query_params.clear()
            st.rerun()

    # ================= 功能 A: 任务管理 (完全保留你喜欢的代码!) =================
    if selected_page == "📦 任务管理":
        try:
            df = pd.read_csv(TASK_DB)
        except:
            df = pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"])

        if is_admin:
            st.title("📊 任务控制台")
            # 这里就是你熟悉的三个标签页，一点没动
            tab1, tab2, tab3 = st.tabs(["⚡ 每日派单", "🔗 岗位分配", "⚙️ 基础设置"])
            
            with tab1: # 派单页
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

            with tab2: # 灵活分配页 (你最喜欢的)
                st.subheader("🔗 岗位分配")
                st.caption("逻辑：在这个店铺 -> 指定这个人 -> 做这些事")
                
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
                    save_config(config)
                    st.success("分配已保存！")

            with tab3: # 设置页 (含产品库权限开关)
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
                        save_config(config)
                        st.success("人员已更新")
                        st.rerun()
                
                with c2:
                    st.write("**店铺管理**")
                    stores_df = pd.DataFrame(config["stores"], columns=["店铺名称"])
                    edited_stores = st.data_editor(stores_df, num_rows="dynamic")
                    if st.button("💾 保存店铺"):
                        config["stores"] = [s for s in edited_stores["店铺名称"] if s]
                        save_config(config)
                        st.success("店铺已更新")
                
                st.divider()
                st.subheader("🔒 产品库权限控制")
                st.info("在这里决定谁能看左侧的【产品与成本库】菜单。")
                
                # 权限多选框
                staff_uids = [uid for uid, info in config["users"].items() if info["role"] != "admin"]
                current_access = [uid for uid in config.get("product_access", []) if uid in config["users"]]
                
                selected_uids = st.multiselect(
                    "允许以下员工查看产品成本：",
                    options=staff_uids,
                    default=current_access,
                    format_func=lambda x: config["users"][x]["name"]
                )
                if st.button("💾 更新查看权限"):
                    config["product_access"] = selected_uids
                    save_config(config)
                    st.success("权限已保存！未选中的员工将看不到入口。")

        else: # 员工界面
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

    # ================= 功能 B: 产品库 (这是你新加的独立房间) =================
    elif selected_page == "💰 产品与成本库":
        st.title("💰 产品与成本库")
        st.caption("全自由编辑表格：添加货号、成本、供应商信息。Boss 和指定员工可见。")
        
        try:
            prod_df = pd.read_csv(PRODUCT_DB)
        except:
            prod_df = pd.DataFrame(columns=["货号", "产品名称", "成本价(CNY)", "售价(USD)", "供应商", "备注"])

        # 超级表格编辑器
        edited_prod_df = st.data_editor(
            prod_df,
            column_config={
                "货号": st.column_config.TextColumn(required=True),
                "成本价(CNY)": st.column_config.NumberColumn(format="¥%.2f"),
                "售价(USD)": st.column_config.NumberColumn(format="$%.2f"),
                "备注": st.column_config.TextColumn(width="large")
            },
            num_rows="dynamic",
            use_container_width=True,
            key="prod_editor"
        )
        
        if st.button("💾 保存产品数据", type="primary"):
            edited_prod_df.to_csv(PRODUCT_DB, index=False)
            st.success("产品数据已保存！")
