import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
import uuid

# ================= 1. 核心配置与数据结构 =================
CONFIG_FILE = "config_v5.json"
DB_FILE = "tasks.csv"

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

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

def get_name_by_id(config, uid):
    return config["users"].get(uid, {}).get("name", "❌已删除员工")

def get_id_by_name(config, name):
    for uid, info in config["users"].items():
        if info["name"] == name:
            return uid
    return None

config = load_config()

if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)

st.set_page_config(page_title="吴先生团队系统 (修复版)", layout="wide")

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
    st.title("合泰包装盒有限公司")
    user_names = [info["name"] for uid, info in config["users"].items()]
    selected_name = st.selectbox("账户", user_names)
    pwd = st.text_input("密码", type="password")
    remember_me = st.checkbox("记住我 (刷新免登录)")

    if st.button("登录", type="primary"):
        uid = get_id_by_name(config, selected_name)
        if uid and config["users"][uid]["pwd"] == pwd:
            st.session_state.logged_in = True
            st.session_state.user_uid = uid
            if remember_me:
                st.query_params["token"] = uid
            st.rerun()
        else:
            st.error("密码错误")

else:
    # ================= 3. 主工作台 =================
    current_uid = st.session_state.user_uid
    if current_uid not in config["users"]:
        st.session_state.logged_in = False
        st.query_params.clear()
        st.rerun()

    current_user_info = config["users"][current_uid]
    current_name = current_user_info["name"]
    is_admin = (current_user_info.get("role") == "admin")

    with st.sidebar:
        st.title(f"👋 {current_name}")
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.session_state.user_uid = None
            st.query_params.clear()
            st.rerun()

    try:
        df = pd.read_csv(DB_FILE)
    except:
        df = pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"])

    if is_admin:
        tab1, tab2, tab3 = st.tabs(["📊 任务控制台", "🔗人员分配", "⚙️ 人员与店铺管理"])
        
        # === Tab 1: 任务发布 ===
        with tab1:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader("每日工作")
                st.caption("系统会自动过滤掉已删除的店铺或员工，只生成有效的任务。")
            with col2:
                 if st.button("清空历史记录"):
                     pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)
                     st.rerun()

            if st.button("生成今日任务", type="primary"):
                today = datetime.now().strftime("%Y-%m-%d")
                new_rows = []
                count = 0
                
                for item in config.get("assignments", []):
                    if item["store"] not in config["stores"]:
                        continue 
                    
                    assigned_uid = item["uid"]
                    if assigned_uid in config["users"]:
                        real_name = config["users"][assigned_uid]["name"]
                        task_lines = [t.strip() for t in item.get("tasks", "").split('\n') if t.strip()]
                        for t in task_lines:
                            new_rows.append({
                                "日期": today, "店铺": item["store"], "负责人": real_name,
                                "任务内容": t, "状态": "进行中", "完成时间": "-"
                            })
                            count += 1
                
                if new_rows:
                    new_df = pd.DataFrame(new_rows)
                    df = pd.concat([df, new_df], ignore_index=True)
                    df.to_csv(DB_FILE, index=False)
                    st.success(f"发布成功！已生成 {count} 条有效任务。")
                    st.rerun()
                else:
                    st.warning("没有可生成的任务，请检查分配表或店铺/人员名单。")

            st.divider()
            with st.expander("发布临时任务"):
                c1, c2, c3 = st.columns(3)
                with c1: t_store = st.selectbox("店铺", config["stores"])
                with c2: t_user = st.selectbox("给谁", [u["name"] for k,u in config["users"].items() if u["role"] != "admin"])
                with c3: t_text = st.text_input("任务内容")
                if st.button("发布"):
                    new_row = {"日期": datetime.now().strftime("%Y-%m-%d"), "店铺": t_store, 
                               "负责人": t_user, "任务内容": t_text, "状态": "进行中", "完成时间": "-"}
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    df.to_csv(DB_FILE, index=False)
                    st.success("发布成功")
                    st.rerun()
            st.dataframe(df, use_container_width=True)

        # === Tab 2: 灵活分配表 (已修复表头显示问题) ===
        with tab2:
            st.header("🔗 岗位分配")
            st.info("操作提示：点击下方表格的最后一行（虚线框）来添加新分配。")
            
            display_data = []
            for item in config.get("assignments", []):
                uid = item["uid"]
                name = get_name_by_id(config, uid)
                display_data.append({"店铺": item["store"], "员工": name, "指令": item["tasks"]})
            
            # 关键修复：确保即使没数据，也有表头
            df_to_edit = pd.DataFrame(display_data)
            if df_to_edit.empty:
                df_to_edit = pd.DataFrame(columns=["店铺", "员工", "指令"])

            edited_df = st.data_editor(
                df_to_edit,
                column_config={
                    "店铺": st.column_config.SelectboxColumn(options=config["stores"], required=True),
                    "员工": st.column_config.SelectboxColumn(options=[u["name"] for k,u in config["users"].items() if u["role"]!="admin"], required=True),
                    "指令": st.column_config.TextColumn(width="large", help="在这里输入具体工作内容")
                },
                num_rows="dynamic",
                use_container_width=True
            )

            if st.button("💾 保存分配关系"):
                new_assignments = []
                for index, row in edited_df.iterrows():
                    if row["店铺"] and row["员工"]:
                        found_uid = get_id_by_name(config, row["员工"])
                        if found_uid:
                            new_assignments.append({"store": row["店铺"], "uid": found_uid, "tasks": row["指令"]})
                config["assignments"] = new_assignments
                save_config(config)
                st.success("分配已保存！")

        # === Tab 3: 人员与店铺管理 ===
        with tab3:
            st.header("⚙️ 资源管理 (增/删/改)")
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("👥 人员名单")
                st.info("选中行左侧复选框，按 Delete 键可删除员工")
                
                users_list = []
                for uid, info in config["users"].items():
                    users_list.append({"ID (系统自动)": uid, "姓名": info["name"], "密码": info["pwd"], "角色": info["role"]})
                
                edited_users = st.data_editor(
                    pd.DataFrame(users_list),
                    column_config={
                        "ID (系统自动)": st.column_config.TextColumn(disabled=True),
                        "角色": st.column_config.SelectboxColumn(options=["admin", "staff"])
                    },
                    num_rows="dynamic",
                    key="user_edit"
                )
                
                if st.button("💾 保存人员变更"):
                    new_users_dict = {}
                    for index, row in edited_users.iterrows():
                        uid = row["ID (系统自动)"]
                        if not uid or pd.isna(uid):
                            uid = f"u_{str(uuid.uuid4())[:8]}"
                        new_users_dict[uid] = {"name": row["姓名"], "pwd": str(row["密码"]), "role": row["角色"]}
                    
                    config["users"] = new_users_dict
                    save_config(config)
                    st.success("人员名单已更新！")
                    st.rerun()

            with c2:
                st.subheader("🏪 店铺名单")
                st.info("💡 选中行左侧复选框，按 Delete 键可删除店铺")
                stores_df = pd.DataFrame(config["stores"], columns=["店铺名称"])
                edited_stores = st.data_editor(stores_df, num_rows="dynamic")
                if st.button("💾 保存店铺列表"):
                    config["stores"] = [s for s in edited_stores["店铺名称"] if s]
                    save_config(config)
                    st.success("店铺列表已更新！")

    else:
        st.header(f"📋 {current_name} 的工作台")
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
                            df.to_csv(DB_FILE, index=False)
                            st.rerun()
                    else:
                        c3.write(f"已完成 {row['完成时间']}")



