import streamlit as st
import pandas as pd
from datetime import datetime
import os

# 1. 基础配置：定义你的 5 个账号和 4 个店铺
USERS = {
    "Boss": "123456",
    "Creator_A": "aa111",
    "Creator_B": "bb222",
    "Operator_A": "op111",
    "Operator_B": "op222"
}
STORES = ["TikTok店铺-01", "TikTok店铺-02", "TikTok店铺-03", "TikTok店铺-04"]

# 2. 数据初始化：创建一个本地文件存数据
DB_FILE = "tasks.csv"
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)

st.set_page_config(page_title="吴先生的团队管理系统", layout="wide")

# 3. 登录逻辑
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔑 团队管理系统登录")
    user = st.selectbox("选择你的角色", list(USERS.keys()))
    pwd = st.text_input("输入密码", type="password")
    if st.button("登录"):
        if USERS[user] == pwd:
            st.session_state.logged_in = True
            st.session_state.user = user
            st.rerun()
        else:
            st.error("密码错误")
else:
    # 4. 主界面
    st.sidebar.title(f"欢迎，{st.session_state.user}")
    if st.sidebar.button("退出登录"):
        st.session_state.logged_in = False
        st.rerun()

    df = pd.read_csv(DB_FILE)

    # 管理员界面：发布任务
    if st.session_state.user == "Boss":
        st.header("📢 管理中心：发布新任务")
        with st.form("new_task"):
            col1, col2, col3 = st.columns(3)
            with col1: target_store = st.selectbox("选择店铺", STORES)
            with col2: target_user = st.selectbox("指派给", [u for u in USERS.keys() if u != "Boss"])
            with col3: task_text = st.text_input("任务内容（如：拍摄4层珠宝盒视频）")
            if st.form_submit_button("发布任务"):
                new_row = {"日期": datetime.now().strftime("%Y-%m-%d"), "店铺": target_store, 
                           "负责人": target_user, "任务内容": task_text, "状态": "进行中", "完成时间": "-"}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("发布成功！")
        
        st.divider()
        st.header("📊 全员进度总览")
        st.dataframe(df, use_container_width=True)

    # 员工界面：只看自己的任务
    else:
        st.header(f"📅 我的工作清单 ({st.session_state.user})")
        # 核心隔离逻辑：只显示负责人等于当前登录用户的数据
        my_tasks = df[df["负责人"] == st.session_state.user]
        
        if my_tasks.empty:
            st.info("目前没有指派给你的任务。")
        else:
            for index, row in my_tasks.iterrows():
                col1, col2, col3 = st.columns([2, 4, 2])
                with col1: st.write(f"**[{row['店铺']}]**")
                with col2: st.write(row['任务内容'])
                with col3:
                    if row['状态'] == "进行中":
                        if st.button("点击打卡完成", key=f"btn_{index}"):
                            df.at[index, "状态"] = "✅ 已完成"
                            df.at[index, "完成时间"] = datetime.now().strftime("%H:%M:%S")
                            df.to_csv(DB_FILE, index=False)
                            st.rerun()
                    else:
                        st.write(f"已完成 ({row['完成时间']})")
                st.divider()