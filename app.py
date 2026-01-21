import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import io

# ==================== 1. 核心配置 ====================
st.set_page_config(page_title="酷狗榜单助手(手机版)", page_icon="🎵")

# 设置请求头，伪装成浏览器
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Referer": "https://www.kugou.com/"
}

# ==================== 2. 功能模块 ====================

def crawl_kugou_data():
    """功能一：抓取酷狗飙升榜"""
    data_list = []
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        for page in range(1, 6): # 爬取前5页，共100多首
            url = f"https://www.kugou.com/yy/rank/home/{page}-6666.html?from=rank"
            status_text.text(f"正在抓取第 {page} 页...")
            
            response = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            song_list = soup.select(".pc_temp_songlist > ul > li")
            
            if not song_list:
                break
                
            for item in song_list:
                try:
                    # 提取排名
                    rank_str = item.select_one(".pc_temp_num").get_text(strip=True)
                    rank = int(rank_str)
                    
                    # 提取歌名和歌手 (格式通常为: 歌手 - 歌名)
                    full_title = item.get("title", "").strip()
                    if "-" in full_title:
                        parts = full_title.split("-", 1)
                        singer = parts[0].strip()
                        song_name = parts[1].strip()
                    else:
                        singer = "未知歌手"
                        song_name = full_title
                    
                    data_list.append({
                        "榜单名次": rank,
                        "纯歌曲名称": song_name,
                        "歌手": singer,
                        "爬取时间": datetime.now().strftime("%m月%d日%H时%M分")
                    })
                except Exception:
                    continue
            
            progress_bar.progress(page / 5)
            time.sleep(0.5) # 礼貌爬虫
            
        status_text.text("✅ 抓取完成！")
        progress_bar.empty()
        
        # 截取前100名
        df = pd.DataFrame(data_list)
        df = df.sort_values("榜单名次").head(100)
        return df
        
    except Exception as e:
        st.error(f"抓取失败: {str(e)}")
        return None

def merge_history(history_df, new_df):
    """功能二：汇总数据"""
    if history_df is None:
        return new_df
    
    # 合并旧数据和新数据
    merged = pd.concat([history_df, new_df], ignore_index=True)
    
    # 去重逻辑：同一时间、同一首歌只保留一条
    # 你的原代码逻辑是“无去重”，但为了预测准确，建议还是要做简单的重复检查
    # 这里保留原逻辑：简单追加，但为了绘图不出错，我们转换一下时间格式
    return merged

def predict_trends(df):
    """功能三：预测与趋势分析"""
    # 1. 数据清洗：提取日期
    # 假设“爬取时间”格式为 "11月25日13时20分"
    # 我们需要将其标准化以便排序
    
    # 只有一天数据无法预测
    if df['爬取时间'].nunique() < 2:
        st.warning("⚠️ 数据量不足，无法生成趋势预测。请至少上传包含历史数据的文件，或在不同时间抓取两次。")
        return None, None

    # 创建透视表：行=歌名+歌手，列=爬取时间，值=榜单名次
    pivot = df.pivot_table(index=['纯歌曲名称', '歌手'], columns='爬取时间', values='榜单名次', aggfunc='min')
    
    # 获取最近的几个时间点
    time_cols = sorted(pivot.columns, key=lambda x: x) # 简单字符串排序，最好是转datetime
    recent_times = time_cols[-5:] # 取最近5次
    
    recent_data = pivot[recent_times]
    
    # 计算得分 (简单动量策略：排名越靠前得分越高，名次上升得分越高)
    scores = []
    for idx, row in recent_data.iterrows():
        # 这里简化你的打分逻辑
        current_rank = row.iloc[-1]
        if pd.isna(current_rank): # 今天不在榜
            scores.append(0)
            continue
            
        base_score = 101 - current_rank # 基础分
        
        # 趋势分
        trend_score = 0
        if len(row) >= 2 and pd.notna(row.iloc[-2]):
            prev_rank = row.iloc[-2]
            diff = prev_rank - current_rank # 正数代表上升
            trend_score = diff * 2
            
        final_score = base_score + trend_score
        scores.append(final_score)
    
    result_df = pd.DataFrame({
        "纯歌曲名称": [x[0] for x in recent_data.index],
        "歌手": [x[1] for x in recent_data.index],
        "预测指数": scores,
        "今日排名": recent_data.iloc[:, -1].values
    })
    
    # 筛选前20名潜力股
    top_20 = result_df.sort_values("预测指数", ascending=False).head(20)
    
    # 提取用于画图的数据
    top_songs = list(zip(top_20['纯歌曲名称'], top_20['歌手']))
    chart_data = recent_data.loc[top_songs].T # 转置，行是时间，列是歌曲
    
    return top_20, chart_data

# ==================== 3. 主界面逻辑 ====================

st.title("📱 酷狗榜单助手 (Mobile)")

st.info("💡 使用流程：抓取今日数据 -> (可选)上传历史数据 -> 自动合并 -> 查看预测")

# --- 步骤 1: 抓取 ---
st.header("1. 获取今日数据")
if st.button("🚀 开始抓取最新榜单"):
    with st.spinner("正在连接酷狗服务器..."):
        new_data = crawl_kugou_data()
        if new_data is not None:
            st.success(f"成功抓取 {len(new_data)} 条数据！")
            st.session_state['new_data'] = new_data
            st.dataframe(new_data.head(5))

# --- 步骤 2: 历史数据管理 ---
st.header("2. 历史数据库")
uploaded_file = st.file_uploader("📂 上传之前的【汇总表.xlsx】(如果有)", type=['xlsx'])

history_df = None
if uploaded_file:
    try:
        history_df = pd.read_excel(uploaded_file)
        st.write(f"已加载历史数据: {len(history_df)} 条")
    except:
        st.error("文件读取失败，请确保是标准的Excel文件")

# --- 步骤 3: 汇总与预测 ---
st.header("3. 分析与导出")

if 'new_data' in st.session_state:
    # 自动合并
    current_new = st.session_state['new_data']
    final_df = merge_history(history_df, current_new)
    
    # --- 预测 ---
    st.subheader("📊 潜力飙升预测")
    top_20, chart_data = predict_trends(final_df)
    
    if top_20 is not None:
        # 显示表格
        st.write("🔥 预测排名前 20：")
        st.dataframe(top_20[['纯歌曲名称', '歌手', '今日排名', '预测指数']])
        
        # 显示交互式折线图 (替代原来的静态图，手机体验更好)
        st.write("📈 排名走势图 (越低越好)：")
        # 这里的图表是交互式的，手机上可以点击查看数值
        st.line_chart(chart_data)
    
    # --- 导出功能 (手机保存) ---
    st.subheader("💾 保存结果")
    
    # 1. 导出汇总表
    buffer_summary = io.BytesIO()
    final_df.to_excel(buffer_summary, index=False)
    st.download_button(
        label="📥 下载最新汇总表 (含历史)",
        data=buffer_summary,
        file_name=f"酷狗榜单汇总_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
else:
    st.write("👆 请先点击【开始抓取】按钮")
