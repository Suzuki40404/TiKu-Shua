import streamlit as st
import docx
import re
import random
import time

# --- 全局 UI 设置 ---
st.set_page_config(page_title="题库刷", page_icon="📚", layout="centered")

# --- 1. 初始化全局状态 ---
if 'banks' not in st.session_state:
    st.session_state.banks = {}  # {bank_name: db_dict}
if 'favorites_dict' not in st.session_state:
    st.session_state.favorites_dict = {}  # {bank_name: {q_id: q_obj}}
if 'current_bank' not in st.session_state:
    st.session_state.current_bank = ""

# 运行时状态
if 'exam_state' not in st.session_state: st.session_state.exam_state = 'setup'
if 'exam_config' not in st.session_state: st.session_state.exam_config = {}
if 'paper' not in st.session_state: st.session_state.paper = []
if 'time_left' not in st.session_state: st.session_state.time_left = 0
if 'search_results' not in st.session_state: st.session_state.search_results = []

# --- 2. 题库解析模块 ---
def parse_docx(file):
    doc = docx.Document(file)
    text_lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    
    db = {'chapters': {}, 'all': {'单选题': [], '多选题': [], '填空题': [], '判断题': []}}
    current_chapter = "未分类导言"
    current_q, q_type = None, None
    chapter_tags = ["导论", "第一章", "第二章", "第三章", "第四章", "第五章", "第六章", "第七章", "第八章", "第九章", "第十章"]

    for line in text_lines:
        if line in chapter_tags or re.match(r'^第[一二三四五六七八九十]+章$', line):
            current_chapter = line
            if current_chapter not in db['chapters']:
                db['chapters'][current_chapter] = {'单选题': [], '多选题': [], '填空题': [], '判断题': []}
            continue

        m = re.match(r'^\d+\.\s*[（\(](单选题|多选题|填空题|判断题)[）\)]\s*(.*)', line)
        if m:
            if current_q and q_type:
                if current_chapter not in db['chapters']: db['chapters'][current_chapter] = {'单选题': [], '多选题': [], '填空题': [], '判断题': []}
                db['chapters'][current_chapter][q_type].append(current_q)
                db['all'][q_type].append(current_q)
                
            q_type = m.group(1)
            global_idx = len(db['all'][q_type])
            current_q = {
                'id': f"{current_chapter}_{q_type}_{global_idx}", 
                'question': line, 'options': [], 
                'answer': '', 'chapter': current_chapter, 'type': q_type
            }
        elif current_q:
            if line.startswith('正确答案') or line.startswith('答案'): current_q['answer'] = line
            elif re.match(r'^[A-Z][\.．、]', line): current_q['options'].append(line)
            elif line.startswith('(1)') or line.startswith('（1）'): current_q['answer'] += f"\n{line}"
            else:
                if not current_q['options'] and not current_q['answer']: current_q['question'] += f"\n{line}"

    if current_q and q_type:
        if current_chapter not in db['chapters']: db['chapters'][current_chapter] = {'单选题': [], '多选题': [], '填空题': [], '判断题': []}
        db['chapters'][current_chapter][q_type].append(current_q)
        db['all'][q_type].append(current_q)
        
    return db

# --- 3. 公共题目渲染与收藏组件 ---
def render_question_item(q, context_key=""):
    st.markdown(f"<span style='color:gray; font-size:14px;'>[{q['chapter']}]</span>", unsafe_allow_html=True)
    st.write(f"**{q['question']}**")
    if q['options']:
        for opt in q['options']:
            st.write(opt)
            
    fav_dict = st.session_state.favorites_dict.get(st.session_state.current_bank, {})
    is_fav = q['id'] in fav_dict
    
    col1, col2 = st.columns([1.5, 6])
    with col1:
        if st.button("★ 已收藏" if is_fav else "☆ 收藏", key=f"fav_{context_key}_{q['id']}"):
            if is_fav: del fav_dict[q['id']]
            else: fav_dict[q['id']] = q
            st.session_state.favorites_dict[st.session_state.current_bank] = fav_dict
            st.rerun()
    with col2:
        with st.expander("👁️ 查看答案"):
            st.info(q['answer'])

# --- 4. 侧边栏导航与状态栏 ---
st.sidebar.title("📚 题库刷")

uploaded_file = st.sidebar.file_uploader("📂 导入 Word 题库", type="docx")
if uploaded_file is not None:
    bank_name = uploaded_file.name.replace(".docx", "")
    if bank_name not in st.session_state.banks:
        st.session_state.banks[bank_name] = parse_docx(uploaded_file)
        if bank_name not in st.session_state.favorites_dict:
            st.session_state.favorites_dict[bank_name] = {}
        st.session_state.current_bank = bank_name
        st.sidebar.success(f"【{bank_name}】导入成功！")

# 题库切换器
if st.session_state.banks:
    selected_bank = st.sidebar.selectbox("切换当前题库：", list(st.session_state.banks.keys()), 
                                         index=list(st.session_state.banks.keys()).index(st.session_state.current_bank) if st.session_state.current_bank else 0)
    st.session_state.current_bank = selected_bank

menu = ["📖 全局分类题库", "🗂️ 分章节题库", "🔍 题目检索", "⭐ 我的收藏本", "📝 模拟考试 (全真)"]
choice = st.sidebar.radio("导航菜单", menu)

# 空题库拦截器
def check_empty():
    if not st.session_state.current_bank or not st.session_state.banks:
        st.warning("👈 题库为空，请先在左侧导入 Word 文件！")
        return True
    return False

# 分页渲染辅助函数 (无感丝滑分页)
def render_pagination(data_list, page_key, items_per_page=20):
    if not data_list:
        st.info("暂无数据。")
        return
        
    if page_key not in st.session_state: st.session_state[page_key] = 1
    total_pages = max(1, (len(data_list) + items_per_page - 1) // items_per_page)
    
    # 纠正越界页码
    if st.session_state[page_key] > total_pages: st.session_state[page_key] = total_pages
    
    start_idx = (st.session_state[page_key] - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(data_list))
    
    for q in data_list[start_idx:end_idx]:
        render_question_item(q, page_key)
        st.markdown("---")
        
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("◀ 上一页", key=f"prev_{page_key}", disabled=st.session_state[page_key] <= 1):
            st.session_state[page_key] -= 1
            st.rerun()
    with col2:
        st.markdown(f"<div style='text-align:center; padding-top:8px;'>第 <b>{st.session_state[page_key]} / {total_pages}</b> 页 (共 {len(data_list)} 题)</div>", unsafe_allow_html=True)
    with col3:
        if st.button("下一页 ▶", key=f"next_{page_key}", disabled=st.session_state[page_key] >= total_pages):
            st.session_state[page_key] += 1
            st.rerun()

# --- 模块 1：全局分类题库 ---
if choice == "📖 全局分类题库":
    if not check_empty():
        st.header("📖 全局分类题库")
        db = st.session_state.banks[st.session_state.current_bank]
        
        tabs = st.tabs(["单选题", "多选题", "填空题", "判断题"])
        for idx, t_name in enumerate(["单选题", "多选题", "填空题", "判断题"]):
            with tabs[idx]:
                render_pagination(db['all'].get(t_name, []), f"global_{t_name}")

# --- 模块 2：分章节题库 ---
elif choice == "🗂️ 分章节题库":
    if not check_empty():
        st.header("🗂️ 分章节题库")
        db = st.session_state.banks[st.session_state.current_bank]
        chapters = list(db['chapters'].keys())
        
        if chapters:
            selected_chapter = st.selectbox("请选择要复习的章节：", chapters)
            tabs = st.tabs(["单选题", "多选题", "填空题", "判断题"])
            for idx, t_name in enumerate(["单选题", "多选题", "填空题", "判断题"]):
                with tabs[idx]:
                    render_pagination(db['chapters'][selected_chapter].get(t_name, []), f"chap_{selected_chapter}_{t_name}")

# --- 模块 3：题目检索 ---
elif choice == "🔍 题目检索":
    if not check_empty():
        st.header("🔍 题目检索")
        db = st.session_state.banks[st.session_state.current_bank]
        
        col1, col2 = st.columns([7, 3])
        keyword = col1.text_input("关键字检索：", placeholder="输入题干或选项关键词...")
        scope = col2.selectbox("检索范围：", ["全部章节"] + list(db['chapters'].keys()))
        
        if keyword:
            results = []
            def match_keyword(q): return keyword in (q['question'] + "".join(q['options']))
            
            if scope == "全部章节":
                for t in db['all']:
                    results.extend([q for q in db['all'][t] if match_keyword(q)])
            else:
                for t in db['chapters'][scope]:
                    results.extend([q for q in db['chapters'][scope][t] if match_keyword(q)])
                    
            render_pagination(results, f"search_{keyword}_{scope}")

# --- 模块 4：收藏本 ---
elif choice == "⭐ 我的收藏本":
    if not check_empty():
        st.header("⭐ 我的收藏本")
        favs = list(st.session_state.favorites_dict.get(st.session_state.current_bank, {}).values())
        if not favs:
            st.info("当前题库的收藏本还是空的呢，去刷题时点击「☆ 收藏」吧！")
        else:
            render_pagination(favs, "favorites")

# --- 模块 5：全真模拟考场 ---
elif choice == "📝 模拟考试 (全真)":
    if not check_empty():
        db = st.session_state.banks[st.session_state.current_bank]
        
        # [配置阶段]
        if st.session_state.exam_state == 'setup':
            st.header("⚙️ 考前参数设置")
            st.markdown("---")
            exam_time = st.number_input("考试总时长 (分钟)", min_value=1, value=60)
            
            cols = st.columns(4)
            types = ["单选题", "多选题", "填空题", "判断题"]
            configs = {}
            total_score, total_count = 0, 0
            
            for i, t in enumerate(types):
                with cols[i]:
                    max_q = len(db['all'][t])
                    cnt = st.number_input(f"{t} 数量 (库余{max_q})", min_value=0, max_value=max_q, value=min(10, max_q))
                    score = st.number_input(f"{t} 每题分值", min_value=1, value=2, key=f"score_{t}")
                    configs[t] = {'count': cnt, 'score': score}
                    total_score += cnt * score
                    total_count += cnt
                    
            st.info(f"💡 当前试卷：**{total_count}** 题 ｜ 满分：**{total_score}** 分")
            
            if st.button("🚀 生成试卷并开始作答", use_container_width=True):
                paper = []
                for t in types: paper.extend(random.sample(db['all'][t], configs[t]['count']))
                
                st.session_state.paper = paper
                st.session_state.exam_config = configs
                st.session_state.time_left = exam_time * 60
                st.session_state.exam_state = 'running'
                
                # 清理旧作答
                for key in list(st.session_state.keys()):
                    if key.startswith("ans_") or key.startswith("mark_"): del st.session_state[key]
                st.rerun()

        # [作答阶段]
        elif st.session_state.exam_state == 'running':
            st.header("📝 答题区")
            
            # 答题卡总览
            with st.expander("📊 作答详情看板 (蓝:已答 | 灰:未答 | 🚩:已标记)", expanded=True):
                grid_html = "<div style='display:flex; flex-wrap:wrap; gap:8px;'>"
                for idx, q in enumerate(st.session_state.paper):
                    q_id = q['id']
                    ans = st.session_state.get(f"ans_{q_id}")
                    is_answered = ans is not None and ans != "" and ans != []
                    is_marked = st.session_state.get(f"mark_{q_id}", False)
                    bg_color = "#1a73e8" if is_answered else "#f8f9fa"
                    text_color = "white" if is_answered else "black"
                    flag = "🚩" if is_marked else ""
                    grid_html += f"<div style='width: 45px; height: 35px; background: {bg_color}; color: {text_color}; border: 1px solid #dadce0; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 14px;'>{idx+1}{flag}</div>"
                grid_html += "</div>"
                st.markdown(grid_html, unsafe_allow_html=True)
            st.markdown("---")

            for idx, q in enumerate(st.session_state.paper):
                q_id = q['id']
                score = st.session_state.exam_config[q['type']]['score']
                st.markdown(f"**第 {idx + 1} 题** ({q['type']} - {score}分)")
                st.write(q['question'])
                
                c_input, c_mark = st.columns([8, 2])
                with c_input:
                    if q['type'] == '单选题':
                        st.radio("单选：", options=q['options'], key=f"ans_{q_id}", index=None, label_visibility="collapsed")
                    elif q['type'] == '多选题':
                        st.pills("多选：", options=q['options'], selection_mode="multi", key=f"ans_{q_id}", label_visibility="collapsed")
                    elif q['type'] == '判断题':
                        st.radio("判断：", options=q['options'] if q['options'] else ["对", "错"], key=f"ans_{q_id}", index=None, label_visibility="collapsed")
                    elif q['type'] == '填空题':
                        st.text_input("输入答案：", key=f"ans_{q_id}", placeholder="在此输入你的填空答案...")
                with c_mark:
                    st.toggle("🚩 标记此题", key=f"mark_{q_id}")
                st.markdown("---")
                
            if st.button("📥 确认交卷", type="primary", use_container_width=True):
                st.session_state.exam_state = 'submitted'
                st.rerun()

        # [考后结算阶段：带自动算分看板]
        elif st.session_state.exam_state == 'submitted':
            st.header("🏁 考试结束：成绩报告单")
            
            # --- 自动算分引擎 ---
            obj_score_earned, obj_score_total, sub_score_total = 0, 0, 0
            for q in st.session_state.paper:
                score_per = st.session_state.exam_config[q['type']]['score']
                if q['type'] in ['单选题', '多选题', '判断题']:
                    obj_score_total += score_per
                    std_match = re.search(r'[正]?[确]?[答]?[案]?[：:\s]*([A-Za-z]+|[对错√×])', q['answer'])
                    if std_match:
                        std_ans = std_match.group(1).upper().replace('√', '对').replace('×', '错')
                        user_ans_raw = st.session_state.get(f"ans_{q['id']}")
                        user_extracted = ""
                        if user_ans_raw:
                            if q['type'] == '单选题': 
                                m = re.match(r'^([A-Z])[\.．、]', user_ans_raw)
                                user_extracted = m.group(1) if m else ""
                            elif q['type'] == '多选题':
                                letters = [re.match(r'^([A-Z])[\.．、]', opt).group(1) for opt in user_ans_raw if re.match(r'^([A-Z])[\.．、]', opt)]
                                user_extracted = "".join(sorted(letters))
                            elif q['type'] == '判断题': user_extracted = user_ans_raw
                        if user_extracted == std_ans: obj_score_earned += score_per
                else: sub_score_total += score_per

            # 绘制看板
            col1, col2 = st.columns(2)
            col1.metric("🎯 客观题得分 (系统判定)", f"{obj_score_earned:g} / {obj_score_total:g} 分")
            col2.metric("✍️ 主观题满分参考 (请自评)", f"{sub_score_total:g} 分")
            st.markdown("---")
            
            for idx, q in enumerate(st.session_state.paper):
                user_ans = st.session_state.get(f"ans_{q['id']}", "未作答")
                user_str = " | ".join(sorted(user_ans)) if isinstance(user_ans, list) else user_ans
                
                st.write(f"**第 {idx + 1} 题** ({q['type']} - {st.session_state.exam_config[q['type']]['score']}分)")
                st.write(q['question'])
                st.info(f"**你的作答：** {user_str if user_str else '未作答'}")
                st.success(f"**标准答案：** {q['answer']}")
                st.markdown("---")

            if st.button("🔙 返回重新生成试卷"):
                st.session_state.exam_state = 'setup'
                st.rerun()