import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json

# ================= 1. 核心配置管理 (大脑) =================
CONFIG_FILE = "config.json"
DB_FILE = "tasks.csv"

# 默认配置（如果第一次运行，会用这个）
DEFAULT_CONFIG = {
    "users": {
        "Boss": "123456",
        "小王": "111",
        "小李": "222",
        "运营A": "333",
        "运营B": "444"
    },
    "stores": ["TikTok店铺-01", "TikTok店铺-02", "TikTok店铺-03", "TikTok店铺-04"],
    "templates": {
        "小王": [
            {"store": "TikTok店铺-01", "task": "拍摄 6 层珠宝盒展示视频"},
            {"store": "TikTok店铺-02", "task": "整理素材"}
        ],
        "小李": [
            {"store": "TikTok店铺-03", "task": "寻找红人"},
            {"store": "TikTok店铺-04", "task": "拍摄细节图"}
        ],
        "运营A": [
            {"store": "TikTok店铺-01", "task": "处理订单"},
            {"store": "TikTok店铺-02", "task": "回复客服"}
        ],
        "运营B": [
            {"store": "TikTok店铺-03", "task": "FBT 备货"},
            {"store": "TikTok店铺-04", "task": "竞品监控"}
        ]
    }
}

# 加载配置函数
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        return json.load(f)

# 保存配置函数
def save_config(config):
    with open(CONFIG_FILE, "w", encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

# 初始化
config = load_config()
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)

st.set_page_config(page_title="吴先生团队管理系统", layout="wide")

# ================= 2. 登录逻辑 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🚀 团队任务管理系统")
    st.info("请登录开始工作")
    
    # 动态获取用户列表
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
    
    # 侧边栏
    with st.sidebar:
        st.title(f"👋 欢迎, {current_user}")
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.rerun()
            
    # 读取任务数据
    try:
        df = pd.read_csv(DB_FILE)
    except:
        df = pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"])

    # -------------- Boss 专属界面 --------------
    if current_user == "Boss":
        # 创建两个标签页：一个管任务，一个管设置
        tab1, tab2 = st.tabs(["📊 任务管理看板", "⚙️ 系统设置 (修改人员/任务)"])
        
        with tab1:
            st.subheader("1️⃣ 每日操作")
            if st.button("⚡ 一键发布今日固定任务", type="primary"):
                today = datetime.now().strftime("%Y-%m-%d")
                new_rows = []
                # 从配置里读取模板
                for person, tasks in config["templates"].items():
                    # 确保该员工还在用户列表里
                    if person in config["users"]:
                        for item in tasks:
                            new_rows.append({
                                "日期": today, "店铺": item["store"], "负责人": person, 
                                "任务内容": item["task"], "状态": "进行中", "完成时间": "-"
                            })
                if new_rows:
                    new_df = pd.DataFrame(new_rows)
                    df = pd.concat([df, new_df], ignore_index=True)
                    df.to_csv(DB_FILE, index=False)
                    st.success(f"发布成功！新增 {len(new_rows)} 条任务")
                    st.rerun()
                else:
                    st.warning("模板为空，请先去设置里添加任务！")

            st.divider()
            
            # 手动发布
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
            
            st.subheader("📋 今日进度")
            if st.button("🗑️ 清空历史记录 (新的一天)"):
                 pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)
                 st.rerun()
            st.dataframe(df, use_container_width=True)

        with tab2:
            st.header("🔧 系统配置中心")
            st.caption("在这里修改的内容会立即生效，无需改代码！")
            
            # --- 1. 人员管理 ---
            with st.expander("👥 人员与密码管理", expanded=True):
                # 将字典转换为表格供编辑
                users_df = pd.DataFrame(list(config["users"].items()), columns=["用户名", "密码"])
                edited_users = st.data_editor(users_df, num_rows="dynamic", key="user_editor")
                
                if st.button("💾 保存人员变更"):
                    # 将表格转回字典
                    new_users = dict(zip(edited_users["用户名"], edited_users["密码"]))
                    config["users"] = new_users
                    save_config(config)
                    st.success("人员名单已更新！")
            
            # --- 2. 任务模板管理 ---
            with st.expander("📝 每个人每天的固定任务"):
                target_user = st.selectbox("选择要修改模板的员工", [u for u in config["users"].keys() if u != "Boss"])
                
                # 获取该员工当前的任务列表
                current_tasks = config["templates"].get(target_user, [])
                # 转换为简单的文本格式方便编辑 (每行一个: 店铺名|任务名)
                text_value = "\n".join([f"{t['store']}|{t['task']}" for t in current_tasks])
                
                st.info(f"请按格式输入：店铺名|任务内容 (中间用竖线 | 隔开，一行一条)")
                new_text = st.text_area(f"编辑 {target_user} 的任务", value=text_value, height=150)
                
                if st.button(f"💾 保存 {target_user} 的模板"):
                    new_task_list = []
                    for line in new_text.split("\n"):
                        if "|" in line:
                            parts = line.split("|")
                            new_task_list.append({"store": parts[0].strip(), "task": parts[1].strip()})
                    
                    config["templates"][target_user] = new_task_list
                    save_config(config)
                    st.success(f"{target_user} 的固定任务已更新！")

    # -------------- 员工界面 --------------
    else:
        st.header(f"📋 {current_user} 的待办清单")
        my_tasks = df[df["负责人"] == current_user]
        
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
