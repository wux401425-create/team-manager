import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json

# ================= 1. 核心配置管理 (大脑) =================
CONFIG_FILE = "config_v2.json"
DB_FILE = "tasks.csv"

# 默认配置：这里定义了初始的“积木”
DEFAULT_CONFIG = {
    # 1. 人员名单
    "users": {
        "Boss": "123456",
        "Creator_A": "111",
        "Creator_B": "222",
        "Operator_A": "333",
        "Operator_B": "444"
    },
    # 2. 店铺名单
    "stores": ["TikTok店铺-01", "TikTok店铺-02", "TikTok店铺-03", "TikTok店铺-04"],
    
    # 3. 标准任务 SOP (定义“岗位”要做什么)
    "sop_tasks": {
        "内容任务 (Content)": ["拍摄新品视频 (3条)", "上传素材并填写标题", "回复视频评论"],
        "运营任务 (Ops)": ["处理待发货订单", "FBT 库存预警检查", "竞品价格记录", "回复后台私信"]
    },
    
    # 4. 分配矩阵 (记录哪个店归谁管) - 初始为空，由你在网页上设置
    "allocations": {} 
}

# --- 加载与保存配置 ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        config = json.load(f)
        # 兼容性检查：确保新字段存在
        if "sop_tasks" not in config: config["sop_tasks"] = DEFAULT_CONFIG["sop_tasks"]
        if "allocations" not in config: config["allocations"] = {}
        return config

def save_config(config):
    with open(CONFIG_FILE, "w", encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

# --- 初始化 ---
config = load_config()
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)

st.set_page_config(page_title="吴先生团队管理系统 Pro", layout="wide")

# ================= 2. 登录逻辑 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🚀 团队任务管理系统 Pro")
    st.info("请登录开始工作")
    
    user_list = list(config["users"].keys())
    user = st.selectbox("选择你的角色", user_list)
    pwd = st.text_input("输入密码", type="password")
    
    if st.button("登录", type="primary"):
        if config["users"].get(user) == pwd:
            st.session_state.logged_in = True
            st.session_state.user = user
            st.rerun()
        else:
            st.error("密码错误")

else:
    # ================= 3. 主界面 =================
    current_user = st.session_state.user
    
    with st.sidebar:
        st.title(f"👋 欢迎, {current_user}")
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.rerun()
            
    try:
        df = pd.read_csv(DB_FILE)
    except:
        df = pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"])

    # ------------------ Boss 专属界面 ------------------
    if current_user == "Boss":
        # 三个核心标签页
        tab1, tab2, tab3 = st.tabs(["📊 任务看板", "⚖️ 人员店铺分配 (核心)", "⚙️ 基础配置"])
        
        # --- Tab 1: 任务发布与监控 ---
        with tab1:
            st.subheader("1️⃣ 每日一键发布")
            st.caption("系统会根据你在【分配】页面的设置，自动给对应的人派活！")
            
            if st.button("⚡ 生成今日所有任务", type="primary"):
                today = datetime.now().strftime("%Y-%m-%d")
                new_rows = []
                
                # 遍历所有店铺的分配情况
                allocations = config.get("allocations", {})
                sop = config["sop_tasks"]
                
                count = 0
                for store_name in config["stores"]:
                    # 获取该店铺的分配信息 (如果没分配，就跳过)
                    store_alloc = allocations.get(store_name, {})
                    content_person = store_alloc.get("content_user")
                    ops_person = store_alloc.get("ops_user")
                    
                    # 1. 给内容负责人派活
                    if content_person and content_person in config["users"]:
                        for task in sop["内容任务 (Content)"]:
                            new_rows.append({"日期": today, "店铺": store_name, "负责人": content_person, "任务内容": task, "状态": "进行中", "完成时间": "-"})
                            count += 1
                            
                    # 2. 给运营负责人派活
                    if ops_person and ops_person in config["users"]:
                        for task in sop["运营任务 (Ops)"]:
                            new_rows.append({"日期": today, "店铺": store_name, "负责人": ops_person, "任务内容": task, "状态": "进行中", "完成时间": "-"})
                            count += 1
                
                if new_rows:
                    new_df = pd.DataFrame(new_rows)
                    df = pd.concat([df, new_df], ignore_index=True)
                    df.to_csv(DB_FILE, index=False)
                    st.success(f"成功！已根据最新分配逻辑，生成了 {count} 条任务。")
                    st.rerun()
                else:
                    st.warning("还没有设置店铺分配哦！请去【人员店铺分配】页面设置谁负责哪个店。")

            st.divider()
            
            # 手动发布临时任务
            with st.expander("➕ 发布单条临时任务"):
                c1, c2, c3 = st.columns(3)
                with c1: t_store = st.selectbox("店铺", config["stores"])
                with c2: t_user = st.selectbox("指派给", [u for u in config["users"].keys() if u != "Boss"])
                with c3: t_text = st.text_input("任务内容")
                if st.button("发布"):
                    new_row = {"日期": datetime.now().strftime("%Y-%m-%d"), "店铺": t_store, 
                               "负责人": t_user, "任务内容": t_text, "状态": "进行中", "完成时间": "-"}
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    df.to_csv(DB_FILE, index=False)
                    st.success("发布成功")
                    st.rerun()
            
            # 数据展示
            st.subheader("📋 实时进度")
            if st.button("🗑️ 清空历史记录"):
                 pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)
                 st.rerun()
            st.dataframe(df, use_container_width=True)

        # --- Tab 2: 分配矩阵 (这是你最想要的功能) ---
        with tab2:
            st.header("⚖️ 店铺职责分配矩阵")
            st.info("在这里决定：哪个店 -> 归谁做内容 -> 归谁做运营。修改后立即生效！")
            
            # 构建一个表格供编辑
            alloc_data = []
            current_allocs = config.get("allocations", {})
            users_list = [u for u in config["users"].keys() if u != "Boss"]
            users_options = ["(未分配)"] + users_list
            
            # 每一行是一个店铺
            for store in config["stores"]:
                # 获取当前保存的负责人，如果没有就是(未分配)
                saved = current_allocs.get(store, {})
                c_user = saved.get("content_user", "(未分配)")
                o_user = saved.get("ops_user", "(未分配)")
                
                # 如果这个人在用户列表里找不到(可能被删了)，重置为未分配
                if c_user not in users_list: c_user = "(未分配)"
                if o_user not in users_list: o_user = "(未分配)"
                
                alloc_data.append({
                    "店铺名称": store,
                    "🎥 内容负责人": c_user,
                    "📦 运营负责人": o_user
                })
            
            # 显示可编辑表格
            edited_df = st.data_editor(
                pd.DataFrame(alloc_data),
                column_config={
                    "店铺名称": st.column_config.TextColumn(disabled=True), # 店铺名不能在这里改
                    "🎥 内容负责人": st.column_config.SelectboxColumn(options=users_options, required=True),
                    "📦 运营负责人": st.column_config.SelectboxColumn(options=users_options, required=True)
                },
                hide_index=True,
                use_container_width=True,
                key="allocation_editor"
            )
            
            if st.button("💾 保存分配关系"):
                new_allocs = {}
                for index, row in edited_df.iterrows():
                    store = row["店铺名称"]
                    c_u = row["🎥 内容负责人"]
                    o_u = row["📦 运营负责人"]
                    # 存入配置
                    new_allocs[store] = {
                        "content_user": c_u if c_u != "(未分配)" else None,
                        "ops_user": o_u if o_u != "(未分配)" else None
                    }
                config["allocations"] = new_allocs
                save_config(config)
                st.success("分配逻辑已更新！下次点击【生成今日任务】时将按新逻辑派活。")

        # --- Tab 3: 基础配置 (店铺/人员/SOP) ---
        with tab3:
            st.header("⚙️ 基础资源池")
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader("1. 店铺管理")
                # 将列表转为DataFrame编辑
                stores_df = pd.DataFrame(config["stores"], columns=["店铺名称"])
                edited_stores = st.data_editor(stores_df, num_rows="dynamic", key="store_editor")
                if st.button("💾 保存店铺列表"):
                    # 过滤空行并保存
                    new_stores = [s for s in edited_stores["店铺名称"].tolist() if s]
                    config["stores"] = new_stores
                    save_config(config)
                    st.success("店铺列表已更新！")

            with col_b:
                st.subheader("2. 人员管理")
                users_df = pd.DataFrame(list(config["users"].items()), columns=["用户名", "密码"])
                edited_users = st.data_editor(users_df, num_rows="dynamic", key="user_editor")
                if st.button("💾 保存人员名单"):
                    new_users = dict(zip(edited_users["用户名"], edited_users["密码"]))
                    config["users"] = new_users
                    save_config(config)
                    st.success("人员名单已更新！")
            
            st.divider()
            st.subheader("3. 岗位标准任务 (SOP)")
            st.caption("这里定义：只要是做这个岗位的，不管在哪个店，都要做这些事。")
            
            # 编辑内容任务
            content_tasks_text = "\n".join(config["sop_tasks"]["内容任务 (Content)"])
            new_c_tasks = st.text_area("🎥 内容岗标准任务 (一行一条)", value=content_tasks_text, height=100)
            
            # 编辑运营任务
            ops_tasks_text = "\n".join(config["sop_tasks"]["运营任务 (Ops)"])
            new_o_tasks = st.text_area("📦 运营岗标准任务 (一行一条)", value=ops_tasks_text, height=100)
            
            if st.button("💾 保存 SOP 任务"):
                config["sop_tasks"]["内容任务 (Content)"] = [t.strip() for t in new_c_tasks.split("\n") if t.strip()]
                config["sop_tasks"]["运营任务 (Ops)"] = [t.strip() for t in new_o_tasks.split("\n") if t.strip()]
                save_config(config)
                st.success("SOP 已更新！")

    # ------------------ 员工界面 (不变) ------------------
    else:
        st.header(f"📋 {current_user} 的工作台")
        my_tasks = df[df["负责人"] == current_user]
        
        if my_tasks.empty:
            st.info("今日暂无任务，等待老板分配...")
        else:
            for index, row in my_tasks.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 5, 3])
                    c1.markdown(f"**🏬 {row['店铺']}**")
                    c2.markdown(f"📝 {row['任务内容']}")
                    if row['状态'] == "进行中":
                        if c3.button("打卡", key=f"btn_{index}"):
                            df.at[index, "状态"] = "✅ 已完成"
                            df.at[index, "完成时间"] = datetime.now().strftime("%H:%M:%S")
                            df.to_csv(DB_FILE, index=False)
                            st.rerun()
                    else:
                        c3.write(f"已完成 {row['完成时间']}")
