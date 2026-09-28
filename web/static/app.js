// Deliberation-Lab · 前端
const $ = s => document.querySelector(s);
const CAT = {
  east:    {label:"东方哲思", color:"var(--jade)"},
  west:    {label:"西方哲学", color:"var(--indigo)"},
  metaphysics:{label:"术数玄学", color:"var(--violet)"},
  modern:  {label:"现代思想", color:"var(--teal)"},
  leader:  {label:"领导者",   color:"var(--clay)"},
};
const MODE_HINT = {
  roundtable:"已为「圆桌」模式——选几位智者入席，他们会各抒己见、彼此争辩，最后由书记官为你点透。",
  solo:"已为「独对」模式——选一位智者，与他一对一深谈，他会用自己的方式层层追问。",
  council:"已为「抉择」模式——选几位智者，他们各表立场后，书记官给你一个可落地的决断。",
};

let personas = [];          // 全量人物
let selected = [];          // 选中的 id（保持顺序）
let mode = "roundtable";
let convo = [];             // [{role, content, speaker?}]
let currentSession = null;  // 当前会话在 DB 的 id（每轮自动落库，滚动更新）
let streaming = false;
let controller = null;      // AbortController，用于"停止生成"
let pendingDivination = ""; // 起卦/抽牌结果，随下条消息发送

// ── 初始化（实际调用在文件末尾，确保所有 const 已就绪）──
// 工作台形态：从 ?surface=desktop 进，或作为已安装 PWA 独立窗口启动（standalone）时也算——
// 这样装成 app 后开窗即进工作台，浏览器标签页里仍是完整横向展厅落地页。
const IS_DESKTOP = new URLSearchParams(location.search).get("surface") === "desktop"
  || window.matchMedia("(display-mode: standalone)").matches
  || window.navigator.standalone === true;   // iOS Safari 加到主屏
async function init(){
  if(IS_DESKTOP) document.body.classList.add("surface-desktop");  // 工作台形态，非展厅落地页
  bindUI();
  if(!IS_DESKTOP) mountLandingAscii();   // 桌面端不展示横向展厅首页，省去远山动画/雾气计时器
  await loadPersonas();
  loadHistory();
  if(IS_DESKTOP) enterHall();            // 桌面端：开窗即进入工作台（像 VS Code/Linear，无营销首页）
  try{
    const h = await (await fetch("/api/health")).json();
    $("#modelTag").textContent = h.llm_configured ? `模型 · ${h.model}` : "⚠ 未配置 API key";
  }catch{}
}

async function loadPersonas(){
  personas = await (await fetch("/api/personas")).json();
  const r = $("#roster"); r.innerHTML = "";
  const order = ["east","west","metaphysics","modern","leader"];
  const byCat = {}; personas.forEach(p => (byCat[p.category] ||= []).push(p));
  let n = 0;
  order.forEach(cat => {
    if(!byCat[cat]) return;
    n++;
    const lab = document.createElement("div");
    lab.className = "cat-label";
    lab.textContent = `${String(n).padStart(2,"0")} · ${CAT[cat]?.label||cat}`;
    r.appendChild(lab);
    byCat[cat].forEach(p => r.appendChild(card(p)));
  });
  buildHome();
}

// ── 首页·横向展厅：每位智者一件"展品"（ASCII 像水墨洇边 + 朱印角标）──
let SAGE_ASCII = null;
async function buildHome(){
  const track = $("#sageTrack"); if(!track) return;
  if(!SAGE_ASCII){ try{ SAGE_ASCII = await (await fetch("/sages-ascii.json")).json(); }catch{ SAGE_ASCII = {}; } }
  track.innerHTML = "";
  personas.forEach((p,i) => {
    const card = document.createElement("article");
    card.className = "ex-card"; card.tabIndex = 0;

    const art = document.createElement("div"); art.className = "ex-art ink-bleed";
    const pre = document.createElement("pre"); pre.className = "ex-ascii ascii"; pre.setAttribute("aria-hidden","true");
    pre.textContent = (SAGE_ASCII && SAGE_ASCII[p.id]) || firstChar(p.name);
    art.appendChild(pre);
    art.onclick = () => { if(!track._suppress) openDetail(p.id); };

    const no = document.createElement("span"); no.className="ex-no"; no.textContent = "N° "+String(i+1).padStart(2,"0");
    const h3 = document.createElement("h3"); h3.className="ex-name";
    h3.innerHTML = `<span class="cn">${p.name}</span>${akaSpan(p,"en")}`;
    const kick = document.createElement("p"); kick.className="ex-kicker"; kick.textContent = p.school;
    const q = document.createElement("p"); q.className="ex-quote"; q.textContent = p.one_line||"";
    const seal = document.createElement("span"); seal.className="seal ex-seal"; seal.setAttribute("aria-hidden","true"); seal.textContent = firstChar(p.name);
    const ask = document.createElement("button"); ask.className="ex-ask"; ask.textContent = "请教 →";
    ask.onclick = e => { e.stopPropagation(); if(!track._suppress) askSage(p.id); };

    card.append(art, no, h3, kick, q, seal, ask);
    track.appendChild(card);
  });
  initHomeScroll();
}

// 进度轨 + 箭头 + 拖动横滑（不劫持页面纵向滚动，好滑）
function initHomeScroll(){
  const track = $("#sageTrack"), dot = $("#hmDot"); if(!track) return;
  const upd = () => { const m=track.scrollWidth-track.clientWidth; dot && (dot.style.left=(m>0?track.scrollLeft/m*100:0).toFixed(1)+"%"); };
  track.addEventListener("scroll", upd, {passive:true}); window.addEventListener("resize", upd); upd();
  const step = () => { const c=track.querySelector(".ex-card"); return (c?c.getBoundingClientRect().width:280) + 28; };
  $("#galPrev") && ($("#galPrev").onclick = () => track.scrollBy({left:-step(), behavior:"smooth"}));
  $("#galNext") && ($("#galNext").onclick = () => track.scrollBy({left: step(), behavior:"smooth"}));
  // 拖动横滑（拖动超过阈值才算拖，避免误触卡片）
  let down=false, sx=0, sl=0, moved=0;
  track.addEventListener("pointerdown", e => { if(e.pointerType==="mouse"&&e.button!==0)return; down=true; sx=e.clientX; sl=track.scrollLeft; moved=0; });
  track.addEventListener("pointermove", e => { if(!down)return; const dx=e.clientX-sx; if(Math.abs(dx)>4){moved=dx; track.classList.add("dragging");} track.scrollLeft=sl-dx; });
  const end = () => { if(down&&Math.abs(moved)>6){ track._suppress=true; setTimeout(()=>track._suppress=false,60);} down=false; track.classList.remove("dragging"); };
  track.addEventListener("pointerup", end); track.addEventListener("pointerleave", end); track.addEventListener("pointercancel", end);
}

// 入厅：从展品「请教」进入对话
function askSage(pid){
  mode = "solo";
  document.querySelectorAll(".mode").forEach(b=>b.classList.toggle("active", b.dataset.mode==="solo"));
  selected = [pid]; renderSelection();
  $("#emptyHint") && ($("#emptyHint").textContent = MODE_HINT.solo);
  enterHall();
  setTimeout(()=>$("#input")?.focus(), 300);
}
function enterHall(){ document.body.classList.add("in-hall"); }
function exitHall(){ if(IS_DESKTOP) return; document.body.classList.remove("in-hall"); }  // 桌面端无展厅可返回

function revealObserve(els){
  if(matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)){
    els.forEach(e=>e.classList.add("in")); return;
  }
  const io=new IntersectionObserver(es=>es.forEach(en=>{if(en.isIntersecting){en.target.classList.add("in");io.unobserve(en.target);}}),{threshold:.16});
  els.forEach(e=>io.observe(e));
}

function card(p){
  const el = document.createElement("div");
  el.className = "p-card"; el.dataset.id = p.id;
  el.innerHTML = `
    <div class="seal">${sealInner(p.id, p.name)}</div>
    <div class="p-info">
      <div class="p-name">${p.name}${akaSpan(p,"p-aka")}</div>
      <div class="p-school">${p.school}</div>
    </div>
    <button class="info-btn" title="了解此人">详</button>
    <span class="cat-dot" style="background:${CAT[p.category]?.color||'#bbb'}"></span>`;
  el.onclick = () => toggle(p.id);
  el.querySelector(".info-btn").onclick = e => { e.stopPropagation(); openDetail(p.id); };
  return el;
}
const firstChar = name => (name||"·").replace(/[·•]/g,"")[0];
// 取 aka 里的拉丁文（西方人物），用于"中西结合"的副名；东方人物无拉丁名则不显示
function akaLatin(aka){
  if(!aka) return "";
  const seg = String(aka).split("/").map(s=>s.trim()).find(s=>/[A-Za-z]/.test(s));
  return seg || "";
}
function akaSpan(p, cls){ const a=akaLatin(p.aka); return a?`<span class="${cls}">${a}</span>`:""; }
// 印章：贴伟人像（灰度水墨处理，见 .seal-img）；加载失败回退朱印单字
function sealInner(id, name){
  return `<img class="seal-img" src="/img/av/${id}.jpg" alt="" onerror="this.remove()">${firstChar(name)}`;
}

function toggle(id){
  if(mode === "solo"){ selected = selected[0]===id ? [] : [id]; }
  else{
    selected = selected.includes(id) ? selected.filter(x=>x!==id) : [...selected, id];
  }
  renderSelection();
}

function renderSelection(){
  document.querySelectorAll(".p-card").forEach(c =>
    c.classList.toggle("sel", selected.includes(c.dataset.id)));
  const bar = $("#selectedBar"); bar.innerHTML = "";
  selected.forEach(id => {
    const p = personas.find(x=>x.id===id); if(!p) return;
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `<span class="seal">${sealInner(p.id, p.name)}</span>${p.name}<span class="x">×</span>`;
    chip.querySelector(".x").onclick = () => toggle(id);
    bar.appendChild(chip);
  });
  renderDivBar();
}

// 选中易经/塔罗时，给出"起卦/抽牌"
function renderDivBar(){
  const bar = $("#divBar"); if(!bar) return;
  bar.innerHTML = "";
  if(selected.includes("yijing")){
    const b=document.createElement("button"); b.className="div-btn"; b.textContent="☯ 起卦";
    b.onclick=castHexagram; bar.appendChild(b);
  }
  if(selected.includes("tarot")){
    const b=document.createElement("button"); b.className="div-btn"; b.textContent="🃏 抽牌";
    b.onclick=drawTarot; bar.appendChild(b);
  }
  if(pendingDivination){
    const tag=document.createElement("span"); tag.className="div-tag";
    tag.textContent="本局："+pendingDivination;
    bar.appendChild(tag);
  }
}

// ── 模式切换 ──
function bindUI(){
  document.querySelectorAll(".mode").forEach(b => b.onclick = () => {
    document.querySelectorAll(".mode").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");
    mode = b.dataset.mode;
    if(mode==="solo" && selected.length>1) selected = [selected[0]];
    $("#emptyHint") && ($("#emptyHint").textContent = MODE_HINT[mode]);
    renderSelection();
  });
  const ta = $("#input");
  ta.addEventListener("input", () => { ta.style.height="auto"; ta.style.height=Math.min(ta.scrollHeight,160)+"px"; });
  ta.addEventListener("keydown", e => {
    if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); send(); }
  });
  $("#sendBtn").onclick = () => streaming ? stopGen() : send();
  $("#suggestBtn").onclick = suggest;
  $("#exportBtn").onclick = openReflect;
  $("#newBtn").onclick = resetThread;
  $("#enterBtn").onclick = () => { enterHall(); setTimeout(()=>$("#input")?.focus(),300); };
  $("#backHome") && ($("#backHome").onclick = exitHall);
  // 首页菜单
  const menu = $("#homeMenu");
  $("#menuOpen") && ($("#menuOpen").onclick = () => menu.classList.add("open"));
  $("#menuClose") && ($("#menuClose").onclick = () => menu.classList.remove("open"));
  menu && menu.querySelectorAll("a").forEach(a => a.onclick = () => menu.classList.remove("open"));
  $("#menuEnter") && $("#menuEnter").addEventListener("click", e => { e.preventDefault(); enterHall(); setTimeout(()=>$("#input")?.focus(),300); });
  $("#detailClose").onclick = closeDetail;
  $("#detail").onclick = e => { if(e.target.id==="detail") closeDetail(); };
  $("#menuBtn") && ($("#menuBtn").onclick = () => $(".sidebar").classList.toggle("open"));
  $("#reflectSave").onclick = () => { const r=$("#reflectText").value; closeReflect(); exportNote(r); };
  $("#reflectSkip").onclick = () => { closeReflect(); exportNote(""); };
  $("#reflect").onclick = e => { if(e.target.id==="reflect") closeReflect(); };
  document.addEventListener("keydown", e => { if(e.key==="Escape"){ closeDetail(); closeReflect(); $("#homeMenu")?.classList.remove("open"); } });
}

// ── 自动择贤 ──
async function suggest(){
  const q = $("#input").value.trim();
  if(!q) return toast("先在下方写下你的困惑，我再为你择贤");
  toast("正在为你择贤…");
  try{
    const res = await (await fetch("/api/suggest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q})})).json();
    if(res.picks?.length){
      selected = res.picks.map(p=>p.id).filter(id=>personas.find(x=>x.id===id));
      if(mode==="solo") selected = selected.slice(0,1);
      renderSelection();
      toast("已为你请来：" + selected.map(id=>personas.find(p=>p.id===id)?.name).join("、"));
    }else toast("未能自动选人，请手动挑选");
  }catch{ toast("择贤失败，请手动挑选"); }
}

// ── 发送 / 流式 ──
async function send(){
  if(streaming) return;
  const text = $("#input").value.trim();
  if(!text) return;
  if(selected.length===0) return toast(mode==="solo"?"请先选一位智者":"请先选至少两位智者");
  if(mode!=="solo" && selected.length<2) return toast("圆桌/抉择至少需要两位智者");

  $("#empty")?.remove();
  $("#input").value=""; $("#input").style.height="auto";
  addUser(text);
  convo.push({role:"user", content:text});

  const divin = pendingDivination;       // 本条携带的占卜
  pendingDivination = ""; renderDivBar();

  streaming = true; setBusy(true);
  controller = new AbortController();
  let curBody=null, curName="", buf="", curPushed=true;
  const flush = () => { if(buf.trim() && !curPushed){ convo.push({role:"assistant", content:buf, speaker:curName}); curPushed=true; } };

  try{
    const resp = await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({mode, persona_ids:selected, messages:convo, divination:divin, model:($("#modelSel")?.value||"")}), signal:controller.signal});
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let sseBuf="";
    while(true){
      const {value,done} = await reader.read();
      if(done) break;
      sseBuf += dec.decode(value,{stream:true});
      const parts = sseBuf.split("\n\n"); sseBuf = parts.pop();
      for(const part of parts){
        const line = part.split("\n").find(l=>l.startsWith("data:"));
        if(!line) continue;
        const ev = JSON.parse(line.slice(5).trim());
        if(ev.type==="speaker"){
          flush();                       // 上一位收尾
          [, curBody] = addSay(ev); curName=ev.name; buf=""; curPushed=false;
        }else if(ev.type==="delta"){
          buf += ev.text; curBody.innerHTML = fmt(buf); curBody.classList.add("cursor"); scroll();
        }else if(ev.type==="end"){
          curBody?.classList.remove("cursor"); flush();
        }else if(ev.type==="error"){
          toast("出错：" + ev.message);
        }
      }
    }
  }catch(e){
    if(e.name!=="AbortError") toast("连接中断：" + e.message);
  }
  flush();                               // 中途停止也保住已生成内容
  curBody?.classList.remove("cursor");
  streaming=false; controller=null; setBusy(false);
  $("#exportBtn").disabled = convo.filter(m=>m.role==="assistant").length===0;
  autosave();                            // 每轮自动落库：没导出也不丢
}

// 每轮结束自动保存（滚动更新同一行），不依赖导出
async function autosave(){
  if(!convo.some(m=>m.role==="assistant")) return;
  const title=(convo.find(m=>m.role==="user")?.content||"解惑").slice(0,18);
  try{
    const r=await (await fetch("/api/session/save",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({session_id:currentSession, mode, title, persona_ids:selected, messages:convo})})).json();
    if(r&&r.id){ currentSession=r.id; loadHistory(); }
  }catch{}
}

function stopGen(){ try{ controller?.abort(); }catch{} toast("已停止"); }

// ── 渲染 ──
function addUser(text){
  const m=document.createElement("div"); m.className="msg user";
  m.innerHTML=`<div class="user-bubble">${esc(text).replace(/\n/g,"<br>")}</div>`;
  $("#thread").appendChild(m); scroll();
}
function addSay(ev){
  const isMod = ev.id==="moderator";
  const m=document.createElement("div"); m.className="msg";
  const p = personas.find(x=>x.id===ev.id);
  const accent = isMod ? "var(--ink-faint)" : (CAT[p?.category]?.color || "var(--accent)");
  m.innerHTML=`<div class="say ${isMod?"mod":""}">
    <div class="seal">${isMod?firstChar(ev.name):sealInner(ev.id, ev.name)}</div>
    <div class="say-body">
      <div class="say-head"><span class="say-name">${ev.name}</span>${p?akaSpan(p,"say-aka"):""}<span class="say-school">${ev.school||""}</span></div>
      <div class="say-card" style="--accent:${accent}"></div>
    </div></div>`;
  $("#thread").appendChild(m); scroll();
  return [m, m.querySelector(".say-card")];
}

// 轻量 markdown：标题/列表/引用/粗体；先转义防注入
function esc(s){ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function inlineMd(s){ return esc(s).replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>"); }
function fmt(t){
  const lines=(t||"").split("\n"); let html="", inList=false;
  const closeList=()=>{ if(inList){ html+="</ul>"; inList=false; } };
  for(const raw of lines){
    const line=raw.trimEnd();
    if(/^#{1,6}\s+/.test(line)){ closeList(); html+=`<div class="md-h">${inlineMd(line.replace(/^#{1,6}\s+/,""))}</div>`; }
    else if(/^[-*]\s+/.test(line)){ if(!inList){ html+="<ul>"; inList=true; } html+=`<li>${inlineMd(line.replace(/^[-*]\s+/,""))}</li>`; }
    else if(/^>\s?/.test(line)){ closeList(); html+=`<blockquote>${inlineMd(line.replace(/^>\s?/,""))}</blockquote>`; }
    else if(line===""){ closeList(); html+="<span class='md-br'></span>"; }
    else { closeList(); html+=`<p>${inlineMd(line)}</p>`; }
  }
  closeList();
  return html;
}
function scroll(){ const t=$("#thread"); t.scrollTop=t.scrollHeight; }
function setBusy(b){ const btn=$("#sendBtn"); btn.disabled=false; btn.textContent=b?"停止":"请教"; btn.classList.toggle("stopping",b); }

// ── 导出（含"我的体悟"）/ 历史 ──
function openReflect(){
  if(!convo.length) return;
  $("#reflectText").value=""; $("#reflect").classList.add("show"); $("#reflectText").focus();
}
function closeReflect(){ $("#reflect").classList.remove("show"); }
async function exportNote(reflection){
  if(!convo.length) return;
  const title = (convo.find(m=>m.role==="user")?.content||"解惑").slice(0,18);
  try{
    const res = await (await fetch("/api/export",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({mode, title, persona_ids:selected, messages:convo, reflection:reflection||"", session_id:currentSession})})).json();
    if(res&&res.id) currentSession=res.id;     // 与自动落库的同一行对齐，不另起
    toast("已沉淀进 Obsidian：" + res.path.split("/").pop());
    loadHistory();
  }catch{ toast("导出失败"); }
}
async function loadHistory(){
  try{
    const list = await (await fetch("/api/sessions")).json();
    const h=$("#history"); h.innerHTML="";
    list.slice(0,15).forEach(s=>{
      const el=document.createElement("div"); el.className="h-item";
      el.textContent=`${s.title||"无题"}`; el.title=`${s.created} · ${s.mode}（点击回看）`;
      el.onclick=()=>loadSession(s.id);
      h.appendChild(el);
    });
  }catch{}
}
const MODE_BACK={"独对":"solo","圆桌":"roundtable","抉择":"council"};
async function loadSession(id){
  try{
    const s = await (await fetch(`/api/sessions/${id}`)).json();
    if(!s||s.error) return toast("无法载入该会话");
    mode = MODE_BACK[s.mode] || s.mode || "roundtable";
    currentSession = id;        // 续聊更新这一行，而非另起
    document.querySelectorAll(".mode").forEach(b=>b.classList.toggle("active", b.dataset.mode===mode));
    selected = (s.personas||[]).filter(id=>personas.find(p=>p.id===id));
    convo = s.messages||[];
    renderSelection();
    $("#thread").innerHTML="";
    convo.forEach(m=>{
      if(m.role==="user") addUser(m.content);
      else{
        const p=personaByName(m.speaker);
        const [,body]=addSay({id:p?p.id:(m.speaker==="书记官"?"moderator":""), name:m.speaker||"", school:p?p.school:(m.speaker==="书记官"?"主持":"")});
        body.innerHTML=fmt(m.content);
      }
    });
    $("#exportBtn").disabled = !convo.some(m=>m.role==="assistant");
    $("#landing").classList.add("entered");
    $(".sidebar").classList.remove("open");
    scroll();
  }catch{ toast("无法载入该会话"); }
}
function personaByName(name){ return personas.find(p=>p.name===name); }

// ── 起卦 / 抽牌 ──
const TRIGRAMS={"111":"☰乾","110":"☱兑","101":"☲离","100":"☳震","011":"☴巽","010":"☵坎","001":"☶艮","000":"☷坤"};
function castHexagram(){
  const vals=Array.from({length:6},()=>6+Math.floor(Math.random()*4)); // 6老阴7少阳8少阴9老阳
  const yang=v=>(v%2===1)?"1":"0"; const changing=[];
  vals.forEach((v,i)=>{ if(v===6||v===9) changing.push(i+1); });
  const lower=yang(vals[2])+yang(vals[1])+yang(vals[0]); // 自下而上
  const upper=yang(vals[5])+yang(vals[4])+yang(vals[3]);
  const text=`本卦 上${TRIGRAMS[upper]} 下${TRIGRAMS[lower]}`+(changing.length?`，变爻：第${changing.join("、")}爻`:"，无变爻");
  pendingDivination=text; renderDivBar();
  showDivination("☯ 起卦",text);
}
const ARCANA=["愚者","魔术师","女祭司","皇后","皇帝","教皇","恋人","战车","力量","隐士","命运之轮","正义","倒吊人","死神","节制","恶魔","高塔","星星","月亮","太阳","审判","世界"];
function drawTarot(){
  const pos=["过去","现在","未来"]; const picked=[]; const pool=[...ARCANA];
  const parts=pos.map(pn=>{ const i=Math.floor(Math.random()*pool.length); const card=pool.splice(i,1)[0];
    const rev=Math.random()<0.5?"逆位":"正位"; return `${pn}·${card}(${rev})`; });
  const text=parts.join("，");
  pendingDivination=text; renderDivBar();
  showDivination("🃏 抽牌",text);
}
function showDivination(kind,text){
  $("#empty")?.remove();
  const m=document.createElement("div"); m.className="msg";
  m.innerHTML=`<div class="divination"><span class="div-kind">${kind}</span>${text}</div>`;
  $("#thread").appendChild(m); scroll();
  toast(kind+"已就位，将随下一句一并呈给术数顾问");
}

function resetThread(){
  convo=[]; currentSession=null; streaming=false;   // 新对话 = 新的一行
  $("#thread").innerHTML=`<div class="empty" id="empty">
    <div class="empty-seal">問</div>
    <h2>把心里那件想不通的事，说给他们听</h2>
    <p class="empty-latin">Ask, and the wise shall answer</p>
    <div class="ornament"><span>◆</span></div>
    <p id="emptyHint">${MODE_HINT[mode]}</p></div>`;
  $("#exportBtn").disabled=true;
}

// ── 智者详情面板 ──
const SECTIONS = [
  ["one_line","精神内核"],["worldview","世界观"],["core_ideas","核心思想"],
  ["method","思考方式"],["cases","典型案例"],["signature_phrases","标志名言"],["sources","源典"],["blindspots","局限"],
];
async function openDetail(id){
  const ov=$("#detail"); const body=$("#detailBody");
  body.innerHTML=`<div class="d-loading">展卷中…</div>`;
  ov.classList.add("show");
  try{
    const p = await (await fetch(`/api/persona/${id}`)).json();
    const aka = akaLatin(p.aka);
    const accent = CAT[p.category]?.color || "var(--accent)";
    let html = `<div class="d-head" style="--accent:${accent}">
      <div class="d-seal">${sealInner(p.id,p.name)}</div>
      <div class="d-title">
        <div class="d-name">${p.name}</div>
        ${aka?`<div class="d-aka">${aka}</div>`:""}
        <div class="d-meta">${p.school} · ${p.era}</div>
      </div></div>`;
    html += `<blockquote class="d-quote">${esc(p.one_line||"")}</blockquote>`;
    const s = p.sections||{};
    SECTIONS.slice(1).forEach(([k,label])=>{
      if(!s[k]) return;
      html += `<section class="d-sec"><h4>${label}</h4><div>${fmt(s[k])}</div></section>`;
    });
    html += `<button class="d-invite send" data-id="${p.id}">请他入席</button>`;
    body.innerHTML = html;
    body.querySelector(".d-invite").onclick = ()=>{
      if(!selected.includes(p.id)){ if(mode==="solo") selected=[p.id]; else selected.push(p.id); renderSelection(); }
      closeDetail(); toast(`已请「${p.name}」入席`);
    };
  }catch{ body.innerHTML=`<div class="d-loading">未能载入</div>`; }
}
function closeDetail(){ $("#detail").classList.remove("show"); }

// ── 开场页 ASCII 水墨远山（密度成形）──
const HERO_ASCII = String.raw`
                              v        v
                       .:=+*#%#
                .:-=+*#▒▓███▓▒#*=:.
           .:-=+*#▒▓██████████████▓▒#*=:.
       .:=+*#▒▓██████████████████████████▓▒#+:.
   .-=+*#▒▓██████████████████████████████████████▓▒#+
 ──────────────────────────   ~~~~   ───────────────────────
        ░░▒▒▓▓████              ████▓▓▒▒░░
            |                         ^   ^`;
const _HRAMP = " .:-=+*#%@▒▓█";   // 密度坡道（用于雾气抖动）
let _mistTimer = null;
function mountLandingAscii(){
  const pre = $("#homeAscii"); if(!pre) return;
  const rm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if(rm){ pre.textContent = HERO_ASCII; return; }
  const chars = [...HERO_ASCII], light = "·:-=", t0 = performance.now(), dur = 900;
  (function frame(now){
    const p = Math.min(1,(now-t0)/dur), e = 1-Math.pow(1-p,3);
    let out=""; for(const c of chars){ out += (c==="\n"||c===" ")?c:(Math.random()<e?c:light[(Math.random()*4)|0]); }
    pre.textContent = out;
    if(p<1) requestAnimationFrame(frame); else startMist(pre);
  })(performance.now());
}
// 远山持续动态：少量字符随机升降一档，如雾气在山间流动（克制、低频）
function startMist(pre){
  if(_mistTimer) clearInterval(_mistTimer);
  const base = [...HERO_ASCII];
  const rampIdx = base.map(c => _HRAMP.indexOf(c));   // 非坡道字符为 -1
  pre.textContent = HERO_ASCII;
  _mistTimer = setInterval(() => {
    if(document.body.classList.contains("in-hall")) return;   // 进厅后不跑，省力
    let out = "";
    for(let i=0;i<base.length;i++){
      const c = base[i], ri = rampIdx[i];
      if(c==="\n" || ri <= 0){ out += c; continue; }
      if(Math.random() < 0.05){                                // 5% 轻微抖一档
        const d = Math.random()<0.5 ? -1 : 1;
        out += _HRAMP[Math.max(1, Math.min(_HRAMP.length-1, ri+d))];
      } else out += c;
    }
    pre.textContent = out;
  }, 120);
}

let toastT;
function toast(msg){
  const t=$("#toast"); t.textContent=msg; t.classList.add("show");
  clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove("show"),3200);
}

// 全部定义就绪后再启动
init();
