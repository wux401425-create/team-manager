import streamlit as st
import pandas as pd
from datetime import datetime
import os

# ================= 配置区域（可以在这里修改固定任务） =================
# 1. 账号与密码
USERS = {
    "Boss": "123456",
    "Creator_A": "aa111", 
    "Creator_B": "bb222",
    "Operator_A": "op111",
    "Operator_B": "op222"
}

# 2. 店铺列表
STORES = ["TikTok店铺-01", "TikTok店铺-02", "TikTok店铺-03", "TikTok店铺-04"]

# 3. ⭐ 这里定义每个人的“固定工作内容” (每天必做的事)
# 你可以在这里直接改文字，想加几条加几条
FIXED_TASKS_TEMPLATE = {
    "Creator_A": [
        {"store": "TikTok店铺-01", "task": "拍摄 6 层珠宝盒展示视频 (3条)"},
        {"store": "TikTok店铺-02", "task": "整理并上传昨日素材"}
    ],
    "Creator_B": [
        {"store": "TikTok店铺-03", "task": "寻找红人并发送邀约邮件 (20封)"},
        {"store": "TikTok店铺-04", "task": "拍摄 4 层珠宝盒细节图"}
    ],
    "Operator_A": [
        {"store": "TikTok店铺-01", "task": "处理待发货订单 & 检查库存"},
        {"store": "TikTok店铺-02", "task": "回复后台客服消息"}
    ],
    "Operator_B": [
        {"store": "TikTok店铺-03", "task": "FBT 备货清单核对"},
        {"store": "TikTok店铺-04", "task": "竞品价格监控与记录"}
    ]
}

# ================= 程序逻辑区域 =================
DB_FILE = "tasks.csv"

# 初始化数据文件
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)

st.set_page_config(page_title="吴先生团队管理系统", layout="wide")

# 登录逻辑
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🚀 团队任务管理系统")
    col1, col2 = st.columns([1, 2])
    with col1:
        user = st.selectbox("选择你的角色", list(USERS.keys()))
        pwd = st.text_input("输入密码", type="password")
        if st.button("登录"):
            if USERS.get(user) == pwd:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()
            else:
                st.error("密码错误")
else:
    # 侧边栏
    st.sidebar.title(f"👋 欢迎, {st.session_state.user}")
    if st.sidebar.button("退出登录"):
        st.session_state.logged_in = False
        st.rerun()
    
    # 读取数据
    try:
        df = pd.read_csv(DB_FILE)
    except:
        df = pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"])

    # ================= Boss 界面 =================
    if st.session_state.user == "Boss":
        st.header("🎮 管理控制台")
        
        # --- 新增功能：一键发布固定任务 ---
        st.subheader("1️⃣ 每日例行操作")
        if st.button("⚡ 一键发布今日所有固定任务", type="primary"):
            today = datetime.now().strftime("%Y-%m-%d")
            new_rows = []
            
            # 遍历模板，生成任务
            for person, tasks in FIXED_TASKS_TEMPLATE.items():
                for item in tasks:
                    new_rows.append({
                        "日期": today,
                        "店铺": item["store"],
                        "负责人": person,
                        "任务内容": item["task"],
                        "状态": "进行中",
                        "完成时间": "-"
                    })
            
            # 保存到 CSV
            if new_rows:
                new_df = pd.DataFrame(new_rows)
                df = pd.concat([df, new_df], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success(f"成功发布了 {len(new_rows)} 条固定任务！")
                st.rerun()
            else:
                st.warning("模板里没有任务哦。")

        st.divider()

        # --- 原有功能：手动发布临时任务 ---
        st.subheader("2️⃣ 发布临时/额外任务")
        with st.form("new_task"):
            c1, c2, c3 = st.columns(3)
            with c1: t_store = st.selectbox("选择店铺", STORES)
            with c2: t_user = st.selectbox("指派给", [u for u in USERS.keys() if u != "Boss"])
            with c3: t_text = st.text_input("任务内容")
            if st.form_submit_button("发布临时任务"):
                new_row = {"日期": datetime.now().strftime("%Y-%m-%d"), "店铺": t_store, 
                           "负责人": t_user, "任务内容": t_text, "状态": "进行中", "完成时间": "-"}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("发布成功！")
                st.rerun()

        st.divider()
        
        # --- 数据总览 ---
        st.subheader("📊 今日工作进度")
        # 加上清除数据按钮，方便第二天重置
        if st.button("🗑️ 清空所有历史记录 (新的一天开始)"):
             df = pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"])
             df.to_csv(DB_FILE, index=False)
             st.rerun()
             
        st.dataframe(df, use_container_width=True)

    # ================= 员工界面 =================
    else:
        st.header(f"📋 待办清单: {st.session_state.user}")
        
        # 筛选自己的任务
        my_tasks = df[df["负责人"] == st.session_state.user]
        
        if my_tasks.empty:
            st.info("太棒了！目前没有待办任务。")
        else:
            for index, row in my_tasks.iterrows():
                # 样式优化：用卡片显示
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 5, 3])
                    c1.markdown(f"**🏬 {row['店铺']}**")
                    c2.markdown(f"📝 {row['任务内容']}")
                    
                    if row['状态'] == "进行中":
                        if c3.button("✅ 完成打卡", key=f"btn_{index}"):
                            df.at[index, "状态"] = "✅ 已完成"
                            df.at[index, "完成时间"] = datetime.now().strftime("%H:%M:%S")
                            df.to_csv(DB_FILE, index=False)
                            st.rerun()
                    else:
                        c3.success(f"完成于 {row['完成时间']}")
