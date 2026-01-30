import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json

# ================= 1. 核心配置管理 =================
CONFIG_FILE = "config_v3.json"
DB_FILE = "tasks.csv"

# 默认配置
DEFAULT_CONFIG = {
    # 1. 人员名单
    "users": {
        "Boss": "123456",
        "小王": "111",
        "小李": "222",
        "小张": "333"
    },
    # 2. 店铺名单
    "stores": ["TikTok店铺-01", "TikTok店铺-02", "TikTok店铺-03", "TikTok店铺-04"],
    
    # 3. 万能分配表 (核心升级：不再区分岗位，而是直接记录“谁-在哪个店-做什么”)
    # 结构：List of dicts
    "assignments": [
        {"store": "TikTok店铺-01", "user": "小王", "tasks": "1. 拍摄新品视频\n2. 回复评论"},
        {"store": "TikTok店铺-01", "user": "小李", "tasks": "1. 处理发货\n2. 检查库存"},
        {"store": "TikTok店铺-02", "user": "小王", "tasks": "全权负责所有事务"}
    ]
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        config = json.load(f)
        if "assignments" not in config: config["assignments"] = []
        return config

def save_config(config):
    with open(CONFIG_FILE, "w", encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

config = load_config()
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)

st.set_page_config(page_title="吴先生团队管理系统 Flexible", layout="wide")

# ================= 2. 登录逻辑 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🚀 团队任务管理系统 (灵活版)")
    user = st.selectbox("选择角色", list(config["users"].keys()))
    pwd = st.text_input("密码", type="password")
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
        st.title(f"👋 {current_user}")
        if st.button("退出"):
            st.session_state.logged_in = False
            st.rerun()
            
    try:
        df = pd.read_csv(DB_FILE)
    except:
        df = pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"])

    # ------------------ Boss 专属 ------------------
    if current_user == "Boss":
        tab1, tab2, tab3 = st.tabs(["📊 任务看板", "🔗 岗位与人员分配", "⚙️ 基础设置"])
        
        # --- Tab 1: 任务发布 ---
        with tab1:
            st.subheader("1️⃣ 一键发布")
            st.caption("系统会遍历【岗位与人员分配】表中的每一行，自动生成任务。")
            
            if st.button("⚡ 生成今日任务", type="primary"):
                today = datetime.now().strftime("%Y-%m-%d")
                new_rows = []
                count = 0
                
                # 遍历万能分配表
                for item in config.get("assignments", []):
                    # 确保人还没被删
                    if item["user"] in config["users"]:
                        # 将多行任务拆解
                        task_text = item.get("tasks", "")
                        # 按换行符拆分，如果有序号也支持
                        task_lines = [t.strip() for t in task_text.split('\n') if t.strip()]
                        
                        for t in task_lines:
                            new_rows.append({
                                "日期": today,
                                "店铺": item["store"],
                                "负责人": item["user"],
                                "任务内容": t,
                                "状态": "进行中",
                                "完成时间": "-"
                            })
                            count += 1
                
                if new_rows:
                    new_df = pd.DataFrame(new_rows)
                    df = pd.concat([df, new_df], ignore_index=True)
                    df.to_csv(DB_FILE, index=False)
                    st.success(f"成功发布 {count} 条任务！")
                    st.rerun()
                else:
                    st.warning("分配表是空的，快去 Tab 2 设置吧！")

            st.divider()
            
            # 手动发布
            with st.expander("➕ 临时任务"):
                c1, c2, c3 = st.columns(3)
                with c1: t_store = st.selectbox("店铺", config["stores"])
                with c2: t_user = st.selectbox("给谁", [u for u in config["users"].keys() if u != "Boss"])
                with c3: t_text = st.text_input("做什么")
                if st.button("发布"):
                    new_row = {"日期": datetime.now().strftime("%Y-%m-%d"), "店铺": t_store, 
                               "负责人": t_user, "任务内容": t_text, "状态": "进行中", "完成时间": "-"}
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    df.to_csv(DB_FILE, index=False)
                    st.success("发布成功")
                    st.rerun()
            
            st.subheader("📋 进度表")
            if st.button("🗑️ 清空历史"):
                 pd.DataFrame(columns=["日期", "店铺", "负责人", "任务内容", "状态", "完成时间"]).to_csv(DB_FILE, index=False)
                 st.rerun()
            st.dataframe(df, use_container_width=True)

        # --- Tab 2: 万能分配表 (核心修改) ---
        with tab2:
            st.header("🔗 岗位分配中心")
            st.info("逻辑：选择一个店铺 -> 链接一个员工 -> 写下在这个店他要做的事。")
            st.caption("提示：你可以给同一个店添加多行（分配给不同人），也可以给同一个人添加多行（管多个店）。")
            
            # 准备数据供编辑
            current_assignments = config.get("assignments", [])
            assign_df = pd.DataFrame(current_assignments)
            
            # 如果是空的，初始化列
            if assign_df.empty:
                assign_df = pd.DataFrame(columns=["store", "user", "tasks"])

            # 动态表格编辑器
            edited_df = st.data_editor(
                assign_df,
                column_config={
                    "store": st.column_config.SelectboxColumn("店铺", options=config["stores"], required=True, width="medium"),
                    "user": st.column_config.SelectboxColumn("员工", options=[u for u in config["users"] if u!="Boss"], required=True, width="medium"),
                    "tasks": st.column_config.TextColumn("工作指令 (可换行)", required=True, width="large", help="在这个店具体要做什么？比如：1.拍视频 2.发货")
                },
                num_rows="dynamic", # 允许添加/删除行
                use_container_width=True,
                key="assign_editor"
            )
            
            if st.button("💾 保存分配关系"):
                # 转换回 json 格式
                new_assignments = []
                for index, row in edited_df.iterrows():
                    if row["store"] and row["user"]: # 过滤空行
                        new_assignments.append({
                            "store": row["store"],
                            "user": row["user"],
                            "tasks": row["tasks"]
                        })
                config["assignments"] = new_assignments
                save_config(config)
                st.success("分配已保存！")

        # --- Tab 3: 基础设置 ---
        with tab3:
            st.header("⚙️ 资源管理")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("人员名单")
                users_df = pd.DataFrame(list(config["users"].items()), columns=["用户名", "密码"])
                edited_users = st.data_editor(users_df, num_rows="dynamic")
                if st.button("保存人员"):
                    config["users"] = dict(zip(edited_users["用户名"], edited_users["密码"]))
                    save_config(config)
                    st.success("已更新")
            with c2:
                st.subheader("店铺名单")
                stores_df = pd.DataFrame(config["stores"], columns=["店铺名称"])
                edited_stores = st.data_editor(stores_df, num_rows="dynamic")
                if st.button("保存店铺"):
                    config["stores"] = [s for s in edited_stores["店铺名称"] if s]
                    save_config(config)
                    st.success("已更新")

    # ------------------ 员工界面 ------------------
    else:
        st.header(f"📋 {current_user} 的工作台")
        my_tasks = df[df["负责人"] == current_user]
        if my_tasks.empty:
            st.info("暂无任务")
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
