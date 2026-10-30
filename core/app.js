(function(){
"use strict";

/* ============================ 数据 ============================ */
var DATA = window.__KPOP_DATA__ || {artists:[],releases:[],events:[],generated:""};
var ALL = (DATA.releases || []).slice();
var TODAY = new Date(); TODAY.setHours(0,0,0,0);
var THIS_YEAR = TODAY.getFullYear();

function pad(n){ return n<10 ? "0"+n : ""+n; }
function d2s(d){ return d.getFullYear()+"-"+pad(d.getMonth()+1)+"-"+pad(d.getDate()); }
var TODAY_S = d2s(TODAY);
function parseD(s){ if(!s) return null; var p=s.split("-"); return new Date(+p[0],+p[1]-1,+p[2]); }
function diffDays(s){ var d=parseD(s); if(!d) return null; return Math.round((d-TODAY)/86400000); }

var ART = {};
(DATA.artists||[]).forEach(function(a){ ART[a.name]=a; });

/* 名称展示：中文优先 > 英文 > 原名 */
function dispName(n){
  var a = ART[n];
  if(a && a.zh && a.zh!==n) return {zh:a.zh, en:n};
  return {zh:n, en:null};
}
function plainName(n){ var d=dispName(n); return d.zh || n; }

/* 发行形态：只分 Single / EP / Album 三档（用英文原始类型，不翻译，
   因为翻译会引入二次误差——EP 不等于迷你专，Mini Album 又不一样）。
   后续专、合辑归入 Album，避免筛选时多余一档。 */
function catOf(r){
  var t = (r.rtype||"").toLowerCase();
  if(!t) return "";                       /* 判不出来就留空，不硬猜成 Album */
  if(t.indexOf("mini")>=0 || /\bep\b/.test(t) || t.indexOf("- ep")>=0) return "Mini";
  if(t.indexOf("single")>=0) return "Single";
  if(t.indexOf("album")>=0) return "Album";
  return "";
}
function typeLabel(r){
  var c = r._cat;
  if(c==="Mini") return "EP";
  if(c==="Single") return "Single";
  if(c==="Album") return "Album";
  return "";                              /* 空 → 调用方不显示类型标签 */
}

/* 本地封面文件名：和数据里的 id 一一对应（tools/fetch_covers.py 用同样规则）。
   只保留字母数字，其余换成下划线。 */
function coverFile(id){
  return "covers/" + String(id || "").replace(/[^a-zA-Z0-9]/g, "_") + ".jpg";
}
/* MV 封面文件名：用 BV 号，同样是 fetch_covers.py 里的规则 */
function mvCoverFile(v){
  return "covers/mv_" + String(v || "").replace(/[^a-zA-Z0-9]/g, "_") + ".jpg";
}
/* MV 封面：B站图床有 Referer 防盗链，站外引用一律被拒，所以先试本地那份；
   本地没有 → 试外链；再不行 → 用同艺人某张专辑的封面顶上（站长提的兜底）；
   都没有才隐藏。以前是「加载失败就隐藏」，热门 MV 整排空白就是这个原因。 */
function mvImgTag(m){
  var loc = m.v ? mvCoverFile(m.v) : "";
  var ext = m.i || "";
  var alt = artistCover(m.a);          /* 同艺人的专辑封面兜底 */
  var chain = [loc, ext, alt].filter(Boolean);
  if(!chain.length) return "";
  var src = chain.shift();
  var next = chain.length
    ? "this.onerror=function(){this.onerror=null;this.src='" + esc(chain.shift()) + "';}"
    : "this.style.display='none'";
  return '<img loading="lazy" src="' + esc(src) + '" alt="" onerror="' + next + '">';
}
/* 每个艺人挑一张有封面的专辑，给 MV 兜底用（只算一次） */
var _artistCover = null;
function artistCover(a){
  if(!a) return "";
  if(!_artistCover){
    _artistCover = {};
    for(var i = 0; i < ALL.length; i++){
      var r = ALL[i];
      if(r._img && !_artistCover[r.artist]) _artistCover[r.artist] = r._img;
    }
  }
  return _artistCover[a] || "";
}
/* 图片标签：先试本地封面，失败自动换成外链，再失败才隐藏。
   以前是「加载失败就隐藏」，图一挂整块就空了，观感很差。 */
function imgTag(r, extra){
  var src = r._cover || "";
  var fb = r._img || "";
  if(!src && !fb) return "";
  var e = extra ? " " + extra : "";
  if(src && fb){
    return '<img' + e + ' src="' + esc(src) + '" alt="" '
      + 'onerror="this.onerror=null;this.src=\'' + esc(fb) + '\'">' ;
  }
  return '<img' + e + ' src="' + esc(src || fb) + '" alt="" '
    + 'onerror="this.style.display=\'none\'">';
}

/* 规范化：主数据和分片数据都要过一遍，抽成函数 */
function normOne(r){
  r._cat = catOf(r);
  var a = ART[r.artist];
  r._kind = a&&a.kind ? a.kind : "";
  r._gender = a&&a.gender ? a.gender : "";
  r._agency = (a && (a.parent || a.agency)) ? (a.parent || a.agency) : "";
  r._fandom = a&&a.fandom ? a.fandom : "";
  r._debut = a&&a.debut_year ? a.debut_year : (r.debut_year || null);
  r._dd = diffDays(r.date);
  r._isNew = !!(r._debut && (THIS_YEAR - r._debut) <= 1);
  r._img = (r.image && r.image.indexOf("mzstatic")>=0)
    ? r.image.replace(/\/\d+x\d+bb\.(jpg|png)$/, "/600x600bb.$1")
    : (r.image || "");
  /* 本地封面：cdn.kpopping.com 有防盗链（站外引用一律 403），那批图已经
     下载到 site/covers/。优先用本地的，加载不到再回退外链 —— 这样
     Cloudflare 版（没有 covers 目录）也能自动用回外链，两边都不空白。 */
  r._cover = coverFile(r.id);
  r._tracks = r.tracks || [];
  r._tn = r._tracks.length || 0;
  r._dur = r.durationMs || 0;
  if(!r._dur && r._tracks.length){
    r._dur = r._tracks.reduce(function(s,t){ return s + (t.ms||0); }, 0);
  }
  var d = dispName(r.artist);
  r._hay = [r.artist, d.zh, r.title, r._agency, r._fandom,
            (ART[r.artist]&&ART[r.artist].name_ko)||"", r.rtype||"", r.genre||""]
           .join(" ").toLowerCase();
}
ALL.forEach(normOne);
var DATE_COUNT = {};
ALL.forEach(function(r){ if(r.date) DATE_COUNT[r.date] = (DATE_COUNT[r.date]||0)+1; });

/* ============================ 数据分片 ============================ */
/* 主文件只带最近 RECENT_DAYS 天的发行，更早的按年份切成 data-<年>.js，
   需要时才加载——否则补满 10 年历史后一次性 17MB 会把手机首屏拖死。 */
var YEARS = DATA.years || {};      /* {"2025": 523, ...} */
var LOADED = {}, PENDING = {};

function loadYear(y, cb){
  if(LOADED[y]){ if(cb) cb(); return; }
  if(PENDING[y]) return;      /* 正在加载，等它自己的回调，别重复 render */
  PENDING[y] = 1;
  toast("正在加载 " + y + " 年数据…");
  var s = document.createElement("script");
  s.src = "data/data-" + y + ".js";
  s.onload = function(){
    var c = window["__KPOP_CHUNK_" + y + "__"] || {};
    var arr = c.releases || [];
    arr.forEach(normOne);
    ALL = ALL.concat(arr);
    arr.forEach(function(r){ if(r.date) DATE_COUNT[r.date] = (DATE_COUNT[r.date]||0)+1; });
    LOADED[y] = 1; delete PENDING[y];
    if(cb) cb();
  };
  s.onerror = function(){
    delete PENDING[y];
    toast("加载 " + y + " 年数据失败，请检查网络或刷新重试");
    if(cb) cb();
  };
  document.head.appendChild(s);
}
/* 一次补齐多个年份（按顺序串行加载，避免同时打满请求） */
function loadYears(list, done){
  var i = 0;
  (function next(){
    if(i >= list.length){ if(done) done(); return; }
    loadYear(list[i++], next);
  })();
}
/* 选了更早的时间范围时，自动把涉及的年份补齐 */
var CUTOFF_S = (function(){
  var d = new Date(TODAY); d.setDate(d.getDate() - (DATA.recentDays || 365));
  return d2s(d);
})();
function ensureYears(){
  var f = S.range.from, need = [];
  if(S.tab === "mine"){
    /* 「我的」页：收藏和本命可能来自任何年份，只加载主文件（近一年）会让
       旧专辑刷新后「消失」，用户会以为收藏丢了。这里把所有年份补齐。 */
    need = Object.keys(YEARS).filter(function(y){ return !LOADED[y] && !PENDING[y]; });
  } else if(!f){
    /* 「全部已发布」或在搜索 → 用户想要的就是全部，补齐所有年份 */
    if(S.tab !== "past" && !S.q) return false;
    need = Object.keys(YEARS).filter(function(y){ return !LOADED[y] && !PENDING[y]; });
  } else if(f < CUTOFF_S){
    var y0 = +f.slice(0, 4), y1 = +((S.range.to || f).slice(0, 4));
    for(var y = y1; y >= y0; y--){
      var k = String(y);
      if(YEARS[k] && !LOADED[k] && !PENDING[k]) need.push(k);
    }
  }
  if(!need.length) return false;
  loadYears(need, function(){ render(); });
  return true;
}


/* ============================ 工具 ============================ */
function $(id){ return document.getElementById(id); }
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }
function toast(m){ var t=$("toast"); t.textContent=m; t.classList.add("on");
  clearTimeout(t._t); t._t=setTimeout(function(){ t.classList.remove("on"); },1800); }
function fmtDur(ms){
  if(!ms) return "";
  var s = Math.round(ms/1000), m = Math.floor(s/60), ss = s%60;
  var h = Math.floor(m/60); m = m%60;
  if(h) return h+" 小时 "+m+" 分钟";
  return m+" 分 "+pad(ss)+" 秒";
}
function fmtDurShort(ms){
  if(!ms) return "";
  var s = Math.round(ms/1000), m = Math.floor(s/60), ss = s%60;
  if(m>=60){ var h=Math.floor(m/60); return h+":"+pad(m%60)+":"+pad(ss); }
  return m+":"+pad(ss);
}
function fmtDate(s){
  var d = parseD(s); if(!d) return s||"";
  return d.getFullYear()+" 年 "+(d.getMonth()+1)+" 月 "+d.getDate()+" 日";
}
function searchURL(r){
  return "https://music.apple.com/kr/search?term=" + encodeURIComponent(r.artist+" "+r.title);
}

/* ============================ 状态 ============================ */
var LS = {
  get: function(k,d){ try{ var v=localStorage.getItem("zw_"+k); return v?JSON.parse(v):d; }catch(e){ return d; } },
  set: function(k,v){ try{ localStorage.setItem("zw_"+k, JSON.stringify(v)); }catch(e){} }
};
var favs = LS.get("favs", []);
var bias = LS.get("bias", []);
function isFav(id){ return favs.indexOf(id) >= 0; }
function isBias(n){ return bias.indexOf(n) >= 0; }

var S = {
  view:"home",        /* home | calendar：首页是默认页 */
  tab:"future",       /* future | past | guide | mine | more */
  frange:"f7",        /* 未来子选项：f7 | month | nmonth */
  mine:"fav",         /* 我的子选项：fav | bias */
  q:"", type:"", kind:"", agency:"", sort:"date_asc",
  onlyFav:false, onlyBias:false,
  range:{mode:"quick", from:null, to:null, label:"未来 30 天"},
  showBiasMgr:false, detailId:null,
  showWeek:false,                      /* 打歌节目「本周时间表」是否展开 */
  bdMore:false,                        /* 首页今日生日是否展开全部 */
  calMonth:null, calFrom:null, calTo:null,
  tellKind:"想说的话", tellText:"",   /* 诉说：类别与草稿（重渲染时不丢） */
  djList:null                         /* 随心歌单：抽好的 4 张，换一批才重抽 */
};

/* ============================ 打歌节目 ============================ */
/* 六档打歌节目的播出时间（2026-10 核实）。w = JS getDay()：0 周日 … 6 周六。
   电视台会因节假日、特别节目临时调档，时间仅供参考。 */
var SHOWS = [
  { zh:"THE SHOW",      en:"The Show",         w:2, kst:"18:00", ch:"SBS LIFE" },
  { zh:"冠军秀",         en:"Show Champion",    w:3, kst:"18:00", ch:"MBC M"    },
  { zh:"M! Countdown",  en:"M Countdown",      w:4, kst:"18:00", ch:"Mnet"     },
  { zh:"音乐银行",       en:"Music Bank",       w:5, kst:"17:15", ch:"KBS 2"    },
  { zh:"音乐中心",       en:"Show! Music Core", w:6, kst:"15:15", ch:"MBC"      },
  { zh:"人气歌谣",       en:"Inkigayo",         w:0, kst:"15:20", ch:"SBS"      }
];
var WK = ["周日","周一","周二","周三","周四","周五","周六"];

/* KST → 北京时间：中国比韩国晚 1 小时 */
function kst2cst(t){
  var p = t.split(":"), h = (+p[0] + 23) % 24;
  return (h<10 ? "0" : "") + h + ":" + p[1];
}
function showsOn(w){ return SHOWS.filter(function(s){ return s.w === w; }); }

/* 成员生日：来自 kpopping 档案页（scripts/birthdays.py 抓取） */
var MEMBERS = DATA.members || [];


/* ============================ 图标 ============================ */
/* 全站统一用这套线性图标（24 网格、1.9 描边），不再用 emoji——
   emoji 各平台长得不一样，也是「AI 感」的主要来源。 */
var ICON = {
  search:'<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
  close :'<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  heart :'<path d="M12 20.2s-7.2-4.6-7.2-9.7A4.2 4.2 0 0 1 12 8.2a4.2 4.2 0 0 1 7.2 2.3c0 5.1-7.2 9.7-7.2 9.7z"/>',
  star  :'<path d="M12 3.9l2.6 5.3 5.8.85-4.2 4.1 1 5.75L12 17.1l-5.2 2.8 1-5.75L3.6 10.05l5.8-.85z"/>',
  cal   :'<rect x="3.6" y="5.2" width="16.8" height="15.2" rx="3"/><path d="M8.4 3.2v3.6M15.6 3.2v3.6M3.6 10.2h16.8"/>',
  note  :'<path d="M9.5 17.6V5.6l9.4-2v12"/><circle cx="6.9" cy="17.9" r="2.4"/><circle cx="16.2" cy="15.7" r="2.4"/>',
  head  :'<path d="M4 15.6v-3.3a8 8 0 0 1 16 0v3.3"/><path d="M4 15.6h2.6a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1H4z"/><path d="M20 15.6h-2.6a1 1 0 0 0-1 1v3a1 1 0 0 0 1 1H20z"/>',
  cake  :'<path d="M4.6 20h14.8v-5.4H4.6z"/><path d="M4.6 14.6h14.8V9.9H4.6z"/><path d="M12 9.9V6.5"/><path d="M12 6.5c0-1.3 1-2.3 2.2-2.3 0 1.3-1 2.3-2.2 2.3z"/>',
  grid  :'<rect x="4" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6"/>',
  tv    :'<rect x="3.4" y="5" width="17.2" height="12.8" rx="2.6"/><path d="M9 21h6M12 17.8V21"/>',
  arrow :'<path d="M5 12h13.2M12.9 6.7l5.3 5.3-5.3 5.3"/>',
  play  :'<path d="M8.5 5.6l11 6.4-11 6.4z"/>',
  mv    :'<rect x="3" y="5.5" width="18" height="13" rx="2.6"/><path d="M10 9.6l5 2.4-5 2.4z"/>'
};
/* fill=true 时画实心（收藏已选、本命爱心） */
function ico(name, size, solid){
  var n = size || 16;
  return '<svg class="ico" viewBox="0 0 24 24" width="'+n+'" height="'+n+'"'
    + ' fill="'+(solid ? "currentColor" : "none")+'" stroke="currentColor"'
    + ' stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + (ICON[name] || "") + "</svg>";
}

/* B 站官方 MV（scripts/bilibili.py 抓取，已按播放量降序） */
var MVS = DATA.mvs || [];

function mvURL(m){ return "https://www.bilibili.com/video/" + m.v; }
function fmtPlay(n){
  n = +n || 0;
  if(n >= 100000000) return (n/100000000).toFixed(1) + " 亿";
  if(n >= 10000)     return (n/10000).toFixed(1) + " 万";
  return String(n);
}
/* 首页「热门 MV」：近一个月发行的专辑，找它的主打曲 MV，按播放量降序，最多 6 个。
   匹配办法：MV 标题里出现专辑名（比对前先把引号、空格、大小写全抹掉，
   B 站标题里那些 ‘ ’ 「 」 不然永远对不上）。
   主打没找到也不留空：用同窗口内其它官方 MV 按播放量补足到 6 个。
   MV 只服务于这一块：详情页不挂 MV 入口（用户拍板），mvOf() 已随之删除。 */
var MV_DAYS = 30;          /* 近一个月 */
var MV_MAX  = 6;           /* 板块最多 6 个 */
function mvKey(s){
  return (s || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]/g, "");
}
function mvHot(){
  var now = TODAY.getTime() / 1000, lo = now - MV_DAYS * 86400;
  /* 1) 近一个月发行的专辑 → 艺人 + 专辑名 */
  var want = [], seenRel = {};
  for(var i = 0; i < ALL.length; i++){
    var r = ALL[i];
    if(!r.date) continue;
    var t = Date.parse(r.date + "T00:00:00") / 1000;
    if(!(t <= now && t >= lo)) continue;
    var k = r.artist + "|" + mvKey(r.title);
    if(seenRel[k]) continue;
    seenRel[k] = 1;
    want.push(r);
  }
  /* 2) 先挑「专辑名对得上」的（确定无误的主打 MV），再用同窗口其它官方 MV
        补足候选；最后不管来源，统一按播放量降序取前 6 —— 展示顺序只认播放量，
        不能「先匹配的排前面」，否则 41 万的会排在 370 万前面 */
  var used = {}, pool = [];
  for(var a = 0; a < want.length; a++){
    for(var b = 0; b < MVS.length; b++){
      var m = MVS[b];
      if(used[m.v] || m.a !== want[a].artist) continue;
      if((m.d || 0) < lo || (m.d || 0) > now) continue;
      if(mvKey(m.t).indexOf(mvKey(want[a].title)) >= 0){
        used[m.v] = 1; pool.push(m); break;
      }
    }
  }
  for(var c = 0; c < MVS.length && pool.length < MV_MAX * 3; c++){
    var mv = MVS[c];
    if(used[mv.v]) continue;
    if((mv.d || 0) < lo || (mv.d || 0) > now) continue;
    used[mv.v] = 1; pool.push(mv);
  }
  pool.sort(function(x, y){ return (y.p || 0) - (x.p || 0); });
  var out = pool.slice(0, MV_MAX);
  return {list:out, label: ""};
}

/* 今天过生日的成员。b 形如 2000-04-11，比月日即可。
   同一个人在原团和小分队里会重复出现（HeeJin @ ARTMS / LOONA 1/3），
   这里按「姓名 + 生日」去重，把所属团体合并成一个字符串。 */
function birthdaysToday(){
  var md = TODAY_S.slice(5);
  var out = [], seen = {};
  for(var i=0;i<MEMBERS.length;i++){
    var m = MEMBERS[i];
    if(!m || !m.b || m.b.slice(5) !== md) continue;
    var key = (m.n || "") + "@" + m.b;
    var hit = seen[key];
    if(hit){
      if(hit.g2 === undefined && hit.g !== m.g) hit.g2 = m.g;
      continue;
    }
    var o = { n:m.n, b:m.b, g:m.g, g2:undefined };
    seen[key] = o; out.push(o);
  }
  return out;
}
/* 展示用的团名：'ARTMS · LOONA 1/3' */
function groupLabel(m){
  return m.g2 ? (m.g + " · " + m.g2) : m.g;
}
/* 年龄（按周岁算，生日当天已长一岁） */
function ageOf(b){
  if(!b) return null;
  var y = +b.slice(0,4), m = +b.slice(5,7), d = +b.slice(8,10);
  var a = THIS_YEAR - y;
  var md = TODAY.getMonth()+1, dd = TODAY.getDate();
  if(md < m || (md === m && dd < d)) a--;
  return (a >= 0 && a < 100) ? a : null;
}

/* 时间范围预设。日历弹层里的快捷胶囊行已删（逛日历本身就能选任意范围，
   还有整月 / 整年两个工具），这里只留页面自己还在用的几档。 */
function rangePreset(kind){
  var t = new Date(TODAY), f, to, lb;
  if(kind==="f7"){ f=d2s(t); var e=new Date(t); e.setDate(e.getDate()+7); to=d2s(e); lb="未来 7 天"; }
  else if(kind==="f30"){ f=d2s(t); var e2=new Date(t); e2.setDate(e2.getDate()+30); to=d2s(e2); lb="未来 30 天"; }
  else if(kind==="p365"){ var s2=new Date(t); s2.setDate(s2.getDate()-365); f=d2s(s2); to=d2s(t); lb="过去 1 年"; }
  else if(kind==="pall"){ f=null; to=null; lb="全部已发布"; }
  else if(kind==="month"){ var y=t.getFullYear(), m=t.getMonth(); f=d2s(new Date(y,m,1)); to=d2s(new Date(y,m+1,0)); lb=y+" 年 "+(m+1)+" 月"; }
  else { f=d2s(t); var e4=new Date(t); e4.setDate(e4.getDate()+30); to=d2s(e4); lb="未来 30 天"; }
  return {mode:"quick", kind:kind, from:f, to:to, label:lb};
}

/* ============================ 筛选 ============================ */
/* 各页签实际生效的时间范围：
   未来 → 7 天 / 本月 / 下月；过去 → 日历自选（默认过去 1 年，「清除」即全部已发布）；
   我的、更多 → 不限。 */
function nextMonthRange(){
  var t = TODAY, y = t.getFullYear(), m = t.getMonth() + 1;
  if(m > 11){ m = 0; y++; }
  var from = d2s(new Date(y, m, 1)), to = d2s(new Date(y, m + 1, 0));
  return {mode:"quick", kind:"nmonth", from:from, to:to,
          label:(y + " 年 " + (m + 1) + " 月")};
}
function activeRange(){
  if(S.tab === "future"){
    if(S.frange === "f7")    return rangePreset("f7");
    if(S.frange === "month") return rangePreset("month");
    return nextMonthRange();
  }
  return S.range;
}
function inRange(r){
  var R = activeRange();
  if(R.kind==="pall") return r._dd < 0;
  if(R.from && r.date < R.from) return false;
  if(R.to && r.date > R.to) return false;
  return true;
}
function monthRange(){ return rangePreset("month"); }
function inThisMonth(r){
  var R = monthRange();
  return !!r.date && r.date >= R.from && r.date <= R.to;
}
/* 艺人分类：团体 / Solo / 女团 / 男团 / 混声团 / 女歌手 / 男歌手 */
function kindOK(r){
  var k = S.kind;
  if(!k) return true;
  var isg = (r._kind === "group");
  var g = r._gender;
  if(k==="group") return isg;
  if(k==="solo")  return !!r._kind && !isg;
  if(k==="gg")    return isg && g==="F";
  if(k==="bg")    return isg && g==="M";
  if(k==="coed")  return isg && g==="X";
  if(k==="female")return !isg && !!r._kind && g==="F";
  if(k==="male")  return !isg && !!r._kind && g==="M";
  return true;
}
function applyFilters(list){
  return list.filter(function(r){
    if(S.onlyFav && !isFav(r.id)) return false;
    if(S.onlyBias && !isBias(r.artist)) return false;
    if(S.type && r._cat !== S.type) return false;
    if(!kindOK(r)) return false;
    if(S.agency && r._agency !== S.agency) return false;
    if(!inRange(r)) return false;
    if(S.q && r._hay.indexOf(S.q.toLowerCase()) < 0) return false;
    return true;
  }).sort(function(a,b){
    var ba = isBias(a.artist)?0:1, bb = isBias(b.artist)?0:1;
    if(ba !== bb) return ba - bb;
    if(S.sort==="name") return plainName(a.artist).localeCompare(plainName(b.artist));
    return (a.date||"").localeCompare(b.date||"");
  });
}

/* ============================ 卡片 ============================ */
function ddayHTML(r){
  var dd = r._dd;
  if(dd===null) return '<span class="dday">待定</span>';
  if(dd===0) return '<span class="dday today">D-Day</span>';
  if(dd>0) return '<span class="dday'+(dd<=3?' soon':'')+'">D-'+dd+'</span>';
  return '<span class="dday past">'+Math.abs(dd)+' 天前</span>';
}
function heartHTML(artist, size){
  var on = isBias(artist);
  return '<button class="heart'+(on?' on':'')+'" data-heart="'+esc(artist)+'" '
       + 'title="'+(on?'取消本命':'设为我的本命')+'"'
       + (size?' style="font-size:'+size+'px"':'')+'>'
       + (on ? '&#10084;' : '&#9825;') + '</button>';
}
function cardHTML(r){
  var bi = isBias(r.artist), fa = isFav(r.id);
  var dn = dispName(r.artist);
  var badges = r._isNew ? '<span class="badge new">NEW</span>' : '';
  return '<div class="card'+(bi?' bias':'')+'" data-open="'+esc(r.id)+'">'
    + '<div class="cov">'
    +   '<div class="ph">' + ico('note',22) + '</div>'
    +   imgTag(r, 'loading="lazy"')
    +   ddayHTML(r)
    +   '<button class="favbtn'+(fa?' on':'')+'" data-fav="'+esc(r.id)+'" title="收藏">'+(fa?ico('star',15,true):ico('star',15))+'</button>'
    +   badges
    + '</div>'
    + '<div class="cbody">'
    +   '<div class="ctitle">'+esc(r.title)+'</div>'
    +   '<div class="car">'+heartHTML(r.artist)
    +     '<span class="zh">'+esc(dn.zh)+'</span>'
    +     (dn.en ? '<span class="en">'+esc(dn.en)+'</span>' : '')
    +   '</div>'
    +   '<div class="cmeta">'+(typeLabel(r) ? '<span class="tag">'+esc(typeLabel(r))+'</span>' : '')
    +     (r._tn ? '<span class="tag s">'+r._tn+' 首</span>' : '')
    +     (r._agency ? '<span>'+esc(r._agency)+'</span>' : '')
    +     '<span>'+esc(r.date)+'</span></div>'
    + '</div></div>';
}
function gridHTML(list){
  if(!list.length) return '<div class="empty"><div class="e">' + ico('head',26) + '</div><h3>没有匹配的发行</h3>'
    + '<p>试试调整时间范围或筛选条件</p></div>';
  return '<div class="grid">' + list.map(cardHTML).join("") + '</div>';
}

/* ============================ 从头开始（新人入坑） ============================
   给第一次接触 K-POP 的人看的。全部硬编码，不依赖数据接口——
   这样就算数据源挂了这一页也永远在。写的时候守住两条：
   1) 不编造数据（数字、规则只说确定的，拿不准的不写）
   2) 每个概念都能落到本站的一个动作上（看完就知道下一步干嘛） */
/* 从头开始：内容来自站长的《KPOP宝典》，面向没追过 K-POP 的人。
   写法：{ t:小节标题, s:副标题, p:[整段文字], l:[词条表], acts:[跳转按钮] }
   l 的每一项可以是两列（词 → 含义）或三列（名称 → 说明 → 注意）。
   改文案只改中文，别动引号和逗号。 */
var GUIDE = [
  { t:"先认识 K-POP 的基本结构", s:"看懂这些主体和单位，大部分信息就不再陌生"
    , p:[
      "K-POP 通常指围绕韩国流行音乐产业形成的音乐与表演文化。它包含不同风格的作品，参与者也不一定都是韩国人。",
      "追星时你会经常看到这些主体，各自负责的事不一样：",
      "还要分清几种活动单位：",
      "「几代团」的划分可以帮助理解历史背景，但分界存在争议。新人先认识作品和艺人即可，不需要先背一套代际名单。"
    ]
    , l:[
      ["艺人、团体、成员", "唱歌、表演、参加节目、发布内容", "团体活动与成员个人活动可能同时进行"],
      ["经纪公司、厂牌", "艺人管理、作品企划、宣传等", "同一集团下可能有不同厂牌，不能把所有账号混为一谈"],
      ["发行商、音乐平台", "发行、销售、提供音乐服务", "MV、音源或专辑也可能通过发行商的官方渠道发布"],
      ["电视台、节目组", "制作音乐节目、综艺等", "节目规则由节目方制定"],
      ["演出主办方、场馆、票务平台", "筹办、售票、执行演出", "买票与入场要同时看这些主体的公告"],
      ["粉丝组织", "整理资讯、翻译、团购、应援等", "多数由粉丝自发运营，不等于公司官方"],
      ["团体活动", "以组合名义进行"],
      ["Solo", "个人名义的作品或活动", "团体成员发 Solo，不自动意味着退出组合"],
      ["小分队／Unit", "部分成员组成的活动单位"],
      ["限定团／企划团", "有特定企划或期限背景，具体安排看正式说明"],
      ["合作曲／Collaboration", "不同艺人合作，不一定组成长期组合"]
    ]
  },
  { t:"认识一个团，从一张资料卡开始", s:"只记这几项，会轻松很多"
    , p:[
      "建议只整理这些内容：团名及官方写法、成员姓名与艺名（含你常见的中文译名）、出道作品与出道时间、经纪公司、官方账号与公告入口、粉丝名称，以及你喜欢的几首歌和几个舞台。",
      "同一个人可能同时有本名、艺名、韩文名、英文拼写和粉丝昵称。先把官方姓名对应上，再慢慢记昵称，会轻松很多。",
      "成员介绍里常见的「队长、主唱、主舞、Rapper、忙内」等，主要帮助你理解团队分工。不同组合对定位的设置和公开程度不同，没有公开确认的定位不必当真。",
      "不认识全部成员，也不妨碍你先听歌。"
    ]
    , l:[
      ["看一份来源清楚的成员资料", "先把人和名字对上"],
      ["听几首代表作", "找出自己喜欢的风格"],
      ["看一支完整舞台 + 一支练习室", "看编舞和现场"],
      ["看一期有字幕的采访或团体综艺", "了解相处方式"],
      ["有兴趣再补过去的内容", "不必一次补完"]
    ]
  },
  { t:"听歌先找自己的偏好", s:"你不需要喜欢所有热门歌"
    , p:[
      "K-POP 里有流行、舞曲、R&B、嘻哈、摇滚、抒情及各种混合风格。「我喜欢 K-POP」不意味着你需要喜欢所有热门歌。",
      "选择所在地区能够合法使用、拥有相应版权的音乐平台即可，例如国内常用音乐平台，或 Spotify、Apple Music、YouTube Music。同一艺人的不同发行，在不同平台的上架情况可能不同。",
      "听专辑时可以留意三个问题：哪首歌最吸引你？是旋律、人声、节奏、编曲还是歌词吸引你？这些歌适合你在什么场景下反复听？这些感受比「大家都说这首好，所以我必须喜欢」更有用。",
      "几个容易弄错的地方：音乐平台上的歌曲与 MV 是不同内容，MV 可能包含剧情、前奏或额外音效；翻唱、混音、现场版、重新录制版不是同一条录音；歌词翻译包含理解和取舍，有疑问时比较不同翻译并查看原文背景；订阅内的离线缓存与购买音乐文件是不同权益，能保存多久要看服务说明；搜索结果里可能混入翻唱、同名艺人或用户上传内容，注意核对艺人主页、专辑和发行信息。"
    ]
    , l:[
      ["从吸引你的那首歌开始", "先建立第一印象"],
      ["听同一张专辑，再找两三首喜欢的", "认识专辑整体"],
      ["听其他时期的主打曲", "感受风格变化"],
      ["看现场、乐队版或其他正式改编版本", "同一首歌的另一种样子"],
      ["沿着喜欢的声音、节奏或风格继续探索", "找到更多同类"]
    ]
  },
  { t:"看视频时，先分清看的是哪种内容", s:"MV、直拍、练习室不是一回事"
    , p:[
      "不同类型的内容，能看出的东西不一样，也各有容易误解的地方：",
      "判断演唱或舞蹈时，尽量看完整内容、比较多个场次。音轨、人声、伴奏、现场收音和后期处理可能同时存在，仅凭几秒剪辑很难准确判断。",
      "视频也不一定只发布在艺人自己的频道。公司、发行商、电视台和节目官方都可能是正规发布方，可以从艺人官方公告里的链接确认。"
    ]
    , l:[
      ["MV／M/V", "歌曲、视觉概念、叙事", "剧情和造型不等于艺人现实生活"],
      ["音乐节目舞台", "编舞、服装、镜头、舞台表现", "不同场次的收音和制作方式可能不同"],
      ["Dance Practice／练习室", "完整编舞、队形、动作细节", "可能是专门拍摄的正式内容"],
      ["Performance Video", "表演设计、舞蹈与镜头配合", "不一定是演唱会现场"],
      ["Fancam／直拍", "某位成员或某个机位的表现", "有官方直拍，也有粉丝拍摄"],
      ["Full Cam／全景", "团体队形与整体舞台", "通常减少切镜头，便于看完整动作"],
      ["Behind／幕后", "排练、拍摄、准备过程", "仍然经过选择和剪辑"],
      ["综艺、直播、采访", "互动方式、表达、兴趣", "节目设定和翻译会影响理解"],
      ["演唱会片段", "现场编排、氛围、互动", "短片段不能代表整场状态"]
    ]
  },
  { t:"看懂一次「回归」", s:"一轮回归里都有什么"
    , p:[
      "回归／Comeback，在 K-POP 语境里通常指艺人推出新作品并展开相关宣传，不一定意味着之前退圈或长期消失。",
      "一轮回归可能包含：宣布新作 → 公布日程 → 概念照、曲目表、试听或预告 → 正式发行 → 音乐节目、采访、综艺、签售等宣传。实际顺序和内容因艺人而异，不是每张作品都有实体专辑、MV、打歌活动或签售。",
      "常见发行名称：",
      "专辑名不一定等于主打曲名。找 MV 或舞台时，直接搜索「艺人＋歌曲名」通常更准确。",
      "看日程一定注意时区：韩国标准时间 KST＝UTC+9；北京、香港时间为 UTC+8。例如 18:00 KST 对应北京时间、香港时间 17:00。发行、MV 首播、直播和预售结束时间可能各不相同，适合分别记在日历里。"
    ]
    , l:[
      ["Single／单曲", "一种发行形式，可能包含不止一条音轨"],
      ["Digital Single／数字单曲", "以数字方式发行，不代表一定有实体版"],
      ["EP／Mini Album／迷你专辑", "通常比正规专辑篇幅短，具体以官方标注为准"],
      ["Full Album／正规专辑", "通常是规模较完整的专辑企划，没有必要靠曲目数自行判定"],
      ["Title Track／主打曲", "主要用于这轮宣传的歌曲，可能不止一首"],
      ["B-side／收录曲", "专辑中主打之外的歌曲，也可能另外拍视频或表演"],
      ["Pre-release／先行曲", "在完整作品推出前先发布的歌曲"],
      ["Repackage／改版专辑", "在已有专辑基础上调整内容、加入新歌等，新增多少要看曲目表"],
      ["OST", "为影视、游戏等作品推出的原声音乐"],
      ["日专、韩专等", "常用于区分发行市场或企划，仍需查看实际语言、曲目和版本"]
    ]
  },
  { t:"追资讯要建立一条回到原始公告的路", s:"四层信息，可信度不同"
    , p:[
      "信息可以分为四层：",
      "最实用的资讯组合通常是：一个可靠的官方公告入口、一个你使用方便的官方视频入口、一个更新清楚且保留出处的中文翻译或资讯入口、一个记录发行和活动时间的个人日历。",
      "不必同时安装所有社交平台。不同艺人使用的官网、Weverse、社交账号和视频平台不同，从已经确认的官方入口互相跳转会更稳妥。",
      "看到重要消息时依次检查：说的是哪个艺人、哪张作品、哪场活动？原公告是什么时候发布的？有没有修改、延期、取消或补充通知？翻译是否遗漏「不符合资格」「仅限」「除外」等限制？链接是否来自真正的官方入口？",
      "头像、粉丝数和名称里的「官方」都不能单独证明身份。反冒充公告特别提醒过假中奖、私下索款和索取个人资料等情况。"
    ]
    , l:[
      ["艺人、公司、主办方、票务官方公告", "确认发行、活动、资格、售票和变更", "涉及付款、报名、出行时必须核对"],
      ["有编辑责任的媒体报道", "了解新闻和采访", "看日期、引用对象及是否有原文"],
      ["粉丝翻译、资讯站、整理帖", "快速阅读、补背景", "查看来源链接，留意后续更正"],
      ["匿名爆料、聊天截图、猜测帖", "最多作为待确认信息", "不据此付款、出行或指控他人"]
    ]
  },
  { t:"会籍、订阅、私信、礼包要分开看", s:"同在一个平台，也是不同的东西"
    , p:[
      "这些东西可能出现在同一个平台里，但你需要分别看购买页面：",
      "购买前只按商品明确列出的权益做判断。不要把付费沟通界面理解为艺人承诺与你建立私人关系或逐条回复。",
      "开会员也不意味着所有实体礼包自动寄来，会员商品说明里往往把会籍与部分实体商品分开列出。",
      "第一次购买时，建议先保存权益页、付款凭证和续费说明，再决定是否长期保留。"
    ]
    , l:[
      ["官方粉丝会籍／Membership", "有效期、适用地区、具体权益、是否自动续费"],
      ["会员专属内容", "是否包含在会籍内，能看哪些内容，权益何时结束"],
      ["订阅式沟通、私信服务", "订阅对象、计费周期、发送与回复规则"],
      ["Membership Kit／会员礼包", "是否另购、包含什么、运费和发货时间"],
      ["演唱会预售资格", "是否需要会籍、是否另行登记、适用哪一场"],
      ["线上演唱会或直播票", "直播时间、回放期限、设备和观看地区限制"]
    ]
  },
  { t:"「打榜」是个笼统叫法", s:"先弄清你想支持哪项成绩"
    , p:[
      "粉圈说的「打榜」可能混指听歌、购买、看 MV 和投票。它们对应不同系统：",
      "例如在国内音乐平台听歌，与你在 Melon 上的收听是不同记录，国内平台的播放不能直接当作 Melon 播放。是否被某项评选采用，要看评选方公布的数据口径。",
      "评估成绩时先核对四项：哪个榜／哪个地区／哪个统计周期／采用什么数据。没有这些信息，「破纪录」「第一」「销量多少」的含义可能很模糊。"
    ]
    , l:[
      ["在音乐平台听歌", "该平台按规则统计的收听数据", "不自动等于所有国家和平台的榜单成绩"],
      ["购买数字歌曲", "对应商店及采用其数据的统计", "一个平台的购买不能随意换算到其他榜单"],
      ["购买实体专辑", "纳入相应渠道的专辑销量", "不保证计入所有榜"],
      ["观看官方视频", "对应视频平台的有效观看数据", "在其他网站看搬运，不会自动变成原平台播放量"],
      ["参加投票", "那一期、那一奖项的投票结果", "一个 App 的票不能默认用于另一个活动"],
      ["点赞、评论、转发", "对应平台的互动和传播", "不一定是某个奖项的直接计分项"]
    ]
  },
  { t:"实体销量、音源榜、一位、年末奖", s:"四种成绩，分开看"
    , p:[
      "实体专辑榜。两个常见名字是 Circle 和 Hanteo：Circle Album Chart 根据出库单位的批发数量统计并扣除退货；Circle Retail Album Chart 统计零售店销量；Hanteo 实体榜依据接入其统计渠道的销售数据，不应理解为全球所有商店的完整销售总和。所以「Circle 只有出货量一种数据」并不准确，两家的覆盖和口径不同，数字不能直接相加，也不能仅凭差额断言库存或造假。",
      "音源榜。可能涉及播放、下载、去重听众及其他数字使用数据。实时榜、日榜、周榜与综合榜关注的周期不同，名次和综合指数也不是同一种单位。",
      "音乐节目。节目中的「一位」就是当期评选的冠军。不同节目可能采用音源、专辑、视频、广播、投票等项目，但资格和权重会调整，不能用一套公式套所有节目。",
      "年末奖。要看具体年份、具体奖项的候选资格、统计期、评审与投票规则。不是所有奖都由粉丝投票决定，也不是每个奖都只看销量。",
      "看榜单可以增加了解，但排名无法完整代表你个人听到一首歌时的感受。"
    ]
  },
  { t:"支持播放数据，首先是正常使用平台", s:"别为数据打乱作息"
    , p:[
      "对新人而言，可以做到：找到正确的艺人、歌曲和官方视频；按平台允许的方式正常收听、观看；收藏自己喜欢的作品，分享真实感受；对异常计数先查看官方说明。",
      "不要把网络流传的「必须某个音量」「必须间隔几首歌」「必须清除某项记录」等，自动当成通用规则。",
      "Spotify 公开说明中，歌曲播放满 30 秒是其计数基础条件之一；这个条件不能套用到其他平台，也不能保证所有播放进入所有榜单。Spotify 也明确反对制造不真实收听，确认的人工播放不会计入相应公开数据或榜单。",
      "YouTube 会验证观看与互动，数字可能暂缓、冻结或调整；其官方说明把多设备、多窗口等重复制造观看列为低质量播放的例子。因此播放量暂时没动，不必紧张。",
      "不用为了数据打乱作息，也不用购买刷量服务。"
    ]
  },
  { t:"投票前，先确认这张票投给什么", s:"不同投票，主办方和用途都可能不同"
    , p:[
      "你遇到的投票可能是：音乐节目预投票、音乐节目直播投票、年末奖的某个奖项、人气榜或广告奖励活动、媒体与商业平台自办活动、粉丝自发调查。它们的主办方、用途和影响完全可能不同。写着「全球」「人气」或「第一」的投票，也需要先核对活动说明。",
      "第一次参与可以照着做：确认主办方和入口（优先从节目或奖项官方页面进入）→ 确认活动名称、年份和轮次 → 确认投票对象（艺人、组合、歌曲、专辑还是舞台）→ 确认开始结束时间和时区 → 确认资格（地区、年龄、账号类型、验证方式）→ 确认免费票与付费票（是否需要积分、积分如何获得与何时过期）→ 确认次数上限和每日重置时间 → 选择正确候选、完成提交、查看成功提示或记录。",
      "分享截图时，遮住邮箱、账号编号、订单和其他个人资料。",
      "粉丝教程可以帮助你理解界面，但最好确认教程对应的是当前版本、当前活动。节目与 App 的合作关系、货币名称和换票方式都有可能变化。",
      "不向陌生人提供密码、验证码或账号控制权。是否付费由你自己决定，免费参与和不参与都很正常。"
    ]
  },
  { t:"第一次买专辑，先确定你买它的目的", s:"目的不同，适合的商品不同"
    , p:[
      "常见目的包括：想拥有并播放 CD；喜欢写真、包装或实体收藏；想支持一次购买；想收藏某张小卡；想参加指定购买活动。",
      "目的不同，适合的商品不同。例如只想收藏一张确定的小卡，反复购买随机专辑未必适合你；想用 CD 播放器听歌，则要先确认里面真的有普通 CD。",
      "常见版本：",
      "包装叫法不能代替完整商品清单，同一种名称下不同发行的内容也可能不同。",
      "例如 Weverse Albums 通过 QR 等方式把音乐和图片内容导入对应 App，不能直接当作普通 CD 使用；其他平台专辑也要查看自己的说明。"
    ]
    , l:[
      ["Photobook／写真版", "写真和较完整的实体包装", "是否有 CD、随机物数量、体积"],
      ["Jewel Case／珠宝盒版", "常见塑料盒式包装", "曲目、内页和赠品"],
      ["Digipack／纸盒版", "纸质包装", "是否成员封面、是否可选"],
      ["Member Version／成员版", "特定成员的包装或内容", "封面、内页、小卡是否都对应同一人"],
      ["Platform／平台专辑", "通过指定方式领取数字内容", "是否有 CD、使用什么 App、账号与兑换规则"],
      ["KiT 等专用格式", "需要对应系统或应用使用", "兼容设备及具体使用方法"],
      ["黑胶、卡带等", "对应实体介质", "自己是否有匹配的播放设备"]
    ]
  },
  { t:"看懂专辑商品页", s:"重点是内容、赠品、发货和计榜"
    , p:[
      "付款前逐项核对：艺人、专辑名、版本是否正确；是单本、整套、随机发货，还是可以选择版本；是否含普通 CD；固定内容与随机内容分别是什么；随机物是「每本几张」还是「全系列共几款」；是否包含首批限定内容；店铺特典的适用商品、时间和库存条件；发货期、售后、缺件和损坏处理；如关注榜单，商品页是否明确说明计入哪个榜。",
      "几类赠品尤其容易混：",
      "同一张专辑在不同商店可能有不同特典。买一整套，不自动保证随机小卡不重复；有幸运抽，也不自动等于可以获得签售资格。",
      "官方幸运抽商品页会具体说明指定商品与抽取数量；「开始发货时间」也不等于「送到你手里的日期」。",
      "如果你关心「初动」，粉圈通常用它表示发行初期连续七天的专辑销售成绩；实际比较时仍要确认榜单、起算和统计口径，不要只听卖家一句「包计榜」。"
    ]
    , l:[
      ["专内小卡", "专辑官方配置中的卡片，可能随机"],
      ["POB／预售特典", "特定店铺或活动给预售购买者的额外赠品"],
      ["店铺特典", "指定零售商的购买赠品，不一定仅限预售"],
      ["Lucky Draw／幸运抽", "按活动规则抽取的赠品或权益"],
      ["签售相关特典", "可能与指定购买活动有关，是否人人有要看说明"],
      ["饭制赠品", "粉丝或商家自行制作，需与官方物品区分"]
    ]
  },
  { t:"算购专预算，把全部费用算进去", s:"标价不等于到手价"
    , p:[
      "可以使用这个清单：商品价格＋支付或汇率相关费用＋当地运费＋国际运费＋转运、合箱等服务费＋适用税费。",
      "团购、代购还可能有后续「补款」，例如国际运费或国内寄送费。加入前要问清：标价包含哪些费用？后面预计还有哪几次付款？谁持有原始订单、进度能否查询？缺货、退单、漏发、损坏由谁处理？取消和退款按什么规则执行？特典是随机分配、按登记顺序，还是另有规则？",
      "跨境税费不一定都是到货再交，有的平台和地区会在结账时处理。应查看最终结账页，避免预先套用别人的订单经验。",
      "收到商品时，建议留存订单、外包装和清楚的开箱记录，按售后要求及时反映问题。若晒图，遮住地址、电话、运单号和完整兑换码。"
    ]
  },
  { t:"买小卡和二手专辑，先约定交付什么", s:"这些叫法并不完全等价"
    , p:[
      "先分清表述：原封／未拆（卖家声称尚未拆封，仍需确认来源和售后）；拆封专（已打开，具体剩余物品逐项确认）；无卡专／裸专（通常缺少部分随机物，不同卖家叫法可能不同）；仅卡（只出售卡片，不含专辑）；空盒（可能只有包装）；平台专辑二手（实物仍在，也可能已经兑换或绑定数字内容）。",
      "买卡、换卡前确认：是官方专内卡、官方活动特典，还是饭制、复刻物；对应哪张专辑、哪家商店、哪次活动；正反面实拍与具体品相；是否有划痕、压痕、折角、污渍；运费、包装和寄送方式；争议如何通过交易平台处理。",
      "「官卡」不等于一定稀有，「限量」也不等于以后一定涨价。卡片价格会变化，所谓稀有程度也可能缺少可核查依据。",
      "不要只凭塑封、卖家口头「保真」或一张对比图判断真伪；签名商品还要分清亲笔、印刷及具体来源。优先保留平台内的描述、沟通和付款记录。"
    ]
  },
  { t:"签售和视频通话，单独理解报名与抽选", s:"买专辑 ≠ 有资格 ≠ 中签"
    , p:[
      "先区分三个东西：买专辑（获得商品）、获得抽选资格（按活动规则进入候选）、中奖并通过核验（获得该次活动的参加资格）。它们不是同一个状态。",
      "常见流程是：官方公布活动 → 在规定时间购买指定商品 → 按要求报名 → 公布结果 → 核验身份 → 参加活动。有的活动需要额外提交申请，不能默认下单就自动报名。",
      "报名之前必须看清：是线下签售、视频通话，还是其他活动；全员还是指定成员；哪些商品有资格；申请次数或抽选次数如何计算；姓名、证件、账号、通话软件等要求；结果在哪里公布；取消订单是否影响资格；中奖后能否退货或取消；商品、签名品及其他奖品分别怎样发放。",
      "没有可靠的通用「买多少本必中」门槛，往期经验无法保证本次结果。",
      "中奖资格通常与本人身份相关，官方帮助里会要求核对参加人及证件信息，并对签售、通话订单设有专门的取消限制。",
      "参加时提前准备简短的问题或想表达的话，尊重时长与工作人员指引。避免索要私人联系方式、要求羞辱他人、追问未公开关系，或把对方的营业互动当成私人关系。"
    ]
  },
  { t:"线下活动内容不同，名称不等于权益", s:"买 VIP 前逐条读完"
    , p:[
      "各种活动的实际内容差别很大，名称不能替代权益清单：",
      "买「VIP」前，把它包含的权益逐条读完。票种名称听起来高级，并不能说明有某项特定福利。"
    ]
    , l:[
      ["Concert／演唱会", "以音乐表演为主", "不一定包含签名、合影或近距离互动"],
      ["Fanmeeting／粉丝见面会", "可能有聊天、游戏和表演", "不代表每位观众都能单独见面"],
      ["Showcase", "围绕出道、新作品等展示", "媒体场不一定向普通粉丝开放"],
      ["音乐节、拼盘", "多组艺人参与", "某艺人的出演时长未必等于专场"],
      ["Fansign／签售", "按规则签名和交流", "买普通专辑不自动有资格"],
      ["Fancall／视频通话", "按规则进行短时线上交流", "不一定能录屏、转让或改时间"],
      ["Pop-up／快闪店", "限时商品、展示或体验", "不代表艺人会到场"],
      ["Soundcheck／彩排观看", "指定票种或活动的一项权益", "不自动包含在所有 VIP 票中"],
      ["Hi-touch、Send-off 等", "特定形式的互动环节", "形式、距离和参加条件以公告为准"],
      ["线上演唱会、付费直播", "通过指定服务观看", "不等于现场门票，也不保证无限回放"]
    ]
  },
  { t:"买演唱会票，分清资格、申请、付款、出票", s:"四步都不是同一件事"
    , p:[
      "第一步是从艺人、公司或主办方官方公告，找到指定售票渠道。然后分别确认：活动日期、城市和场馆；会员资格要求；是否需要提前登记；采用抢票、抽选还是其他方式；抽选结果、付款和领票的截止时间；购票人、参加人和同行人的姓名规则；票价、手续费、视线限制及退改转让规则。",
      "几个必须分开的概念：预售（公开发售前提供的购票机会）；会员预售登记（满足条件后提交登记）；预售码（获得进入某轮购票的资格或入口）；抽选申请（提交候选申请，等待结果）；中签（得到该轮规定的购票或参加机会）；付款、出票（仍可能需要你继续完成操作）。",
      "票务平台官方说明明确指出，获得预售代码并不保证买到门票。有的活动还要求先在粉丝平台登记，再到票务网站正式申请抽选，只完成第一步并不够。",
      "选座时也要弄清：内场不一定都是站席，需看座位图；站席可能有入场序号和集合要求；看台与内场距离、视角各有取舍；侧面、遮挡或限制视线票要读说明；舞台图可能是示意图，无法保证每个位置的最终视线；同行人不一定能临时更改，连坐也要以实际出票为准。",
      "付款后查看成功订单、金额、参加人、出票状态和后续操作。进入购物车、排进队列或收到扣款提示，都不宜单独作为完整购票成功的判断。"
    ]
  },
  { t:"二手票能不能买，先看允不允许转让", s:"官方规则比卖家保证重要"
    , p:[
      "不同活动可能允许官方转售、限定转让，也可能完全禁止转让和改名。不要先付款，再询问自己能否使用。",
      "特别留意：原购票人与入场人是否必须一致；是否需要实体证件原件；是否核验会籍；票码是否动态更新；截图能否使用；是否必须在指定 App 内出示；是否存在官方转售或退款渠道；同行人是否要跟主购票人一起入场。",
      "「有付款截图」「免费转给亲友」「卖家说包进」，都不能替代官方规则。具体场次中就有禁止无偿转让、要求姓名匹配的规定，也有官方转售渠道与完全禁止转让两种情况并存。",
      "对新人来说，能通过官方规则解释清楚自己如何入场，比卖家的保证更重要。"
    ]
  },
  { t:"看演出前，把出行与现场一起安排好", s:"票不等于入境许可"
    , p:[
      "如果跨城市或跨境参加，先确认：自己是否有符合要求的旅行证件；目的地及中转地的入境、停留要求；未成年人是否需要陪同及相关材料；酒店、交通能否取消或调整；演出结束后如何返回住宿地点；如果延期或取消，自己能承担哪些损失。旅行和入境条件应查对应官方渠道，演出票不等于入境许可。",
      "出发前再检查一遍：",
      "现场是否允许拍照录像，不能凭其他城市的经验判断。有的场次连手机拍摄、录音和直播都禁止；应援物的高度、发光物和行李也可能受限。",
      "现场礼仪可以直接记住：应援物不要挡住后排视线；不站到不允许站立的座位或设施上；不推挤，不占用通道和无障碍空间；艺人讲话时让周围观众能听清；拍摄获准时也不把设备举到别人面前；不向舞台投掷物品，除非活动明确允许特定互动；身体不适或遇到问题，及时找现场工作人员。"
    ]
    , l:[
      ["票与身份", "门票、可接受的证件原件、必要的会员页面"],
      ["时间", "开门、开演、集合、彩排、福利领取时间是否不同"],
      ["电子设备", "手机电量、票务 App、必要网络、场馆允许的充电设备"],
      ["包与物品", "包尺寸、饮水、食物、相机、长焦等限制"],
      ["应援", "应援棒版本、电池、配对方法、手幅尺寸"],
      ["舒适度", "舒适鞋服、天气准备、适当的听力保护"],
      ["返回安排", "散场交通、集合点、同行人联络方式"]
    ]
  },
  { t:"参加音乐节目预录，别照搬演唱会经验", s:"播出时间不等于集合时间"
    , p:[
      "打歌节目现场可能包含预录、正式直播和不同艺人的分别录制。你看到电视播出的时间，不一定是实际集合或录制时间。",
      "参与前要读：申请开放和截止时间；报名、入选、候补及签到规则；年龄、会籍和身份证件要求；是否需要指定实体专辑或音源购买证明；是否需要携带官方应援棒；禁止拍摄、录音和剧透的规定；缺席、迟到与资格转让的处理。",
      "这些材料并非每场都相同，具体场次的官方预录公告会列出核验材料、集合安排和禁止事项，只能按该次活动理解。",
      "不要为尚未确认的参与资格安排无法承受损失的行程，也不要相信陌生人声称能保证带你进入。"
    ]
  },
  { t:"应援可以从听懂一句歌词开始", s:"是表达支持，不是统一任务"
    , p:[
      "常见应援包括：学习官方或明确来源的应援口号；在允许的场合使用应援棒、手幅等；参加生日、周年或回归相关活动；分享作品和自己的真实推荐；参与粉丝组织的广告或其他项目。",
      "应援是表达支持，不是统一任务。不会喊口号、不买应援棒、不参加集体项目，也可以好好看演出。",
      "如果参与需要付款的粉丝项目，先看清：谁组织、谁收款；做什么、预算多少；截止日期和执行计划；是否公开收支和完成证明；未完成时如何处理款项；是否允许退出，规则是什么。",
      "粉丝广告或生日应援，不自动代表艺人或公司授权。有人转发、点赞，也不能进一步推断其与组织者存在私人关系。",
      "现场的应援棒配对、座位绑定和灯光控制，按官方说明操作即可，不要从陌生渠道安装所谓必需工具。"
    ]
  },
  { t:"进入粉丝社群，先学会判断规则和边界", s:"可以参与，也可以安静听歌"
    , p:[
      "你可以参与群聊、论坛、评论区和线下交流，也可以安静地听歌看舞台。",
      "加入社群前建议观察：是否允许新人提问；转发资讯是否保留出处；是否尊重不同成员和不同艺人；是否频繁要求购买、捐款、晒消费记录；是否用辱骂、公开个人资料或群体攻击处理分歧；管理者是否把个人意见包装成「全体粉丝必须」。",
      "粉丝组织、站子和「大粉」可能经验丰富，但他们也可能出错。关注人数和消费金额不能代替事实依据。",
      "对于争议：查看完整原文与时间线；区分事实、推测、翻译和个人评价；给信息核实及当事人回应留出空间；不传播私人资料，不参与围攻；可以调整自己的支持方式。",
      "对于艺人与粉丝之间的边界，也建议明确：不购买或传播私人联系方式、非公开行程和证件信息；不跟车、堵酒店、住所或非公开工作区域；不把偷拍和越界接触当作「关系更近」的证明；尊重艺人、工作人员和其他粉丝的身体与隐私；不把剪辑、CP 二创和营业互动当作现实关系证据。",
      "分享内容时标明来源，尊重创作者和版权要求；不要把整套付费内容、盗录或未经许可的资源分发，当成追星必需步骤。"
    ]
  },
  { t:"黑话可以按场景记", s:"不需要一次背完"
    , p:[
      "下面这些词足以帮助你读懂大部分常见讨论。部分词的用法随社群变化，遇到涉及付款、报名或规则的缩写，直接问清完整含义。"
    ]
    , l:[
      ["爱豆／Idol", "偶像艺人的常见称呼"],
      ["本命／Bias", "自己特别喜欢的成员或艺人"],
      ["担／推", "喜欢、支持某位艺人的说法"],
      ["多担／多推", "同时喜欢多个成员或艺人"],
      ["团粉／团担", "主要喜欢组合整体"],
      ["唯粉／单担", "主要喜欢其中一位成员，本身不等于攻击别人"],
      ["毒唯", "通常指排斥、贬低或攻击其他成员等行为的粉丝称呼"],
      ["CP／嗑 CP", "对某种人物关系产生兴趣或二创，不证明现实关系"],
      ["音饭、舞台粉等", "主要因音乐或舞台喜欢艺人的自我描述"],
      ["路人粉", "兴趣较轻，或偶尔关注"],
      ["入坑", "开始喜欢、深入关注"],
      ["补物料／考古", "看过去发布的内容"],
      ["退坑／淡圈", "结束或减少关注"],
      ["墙头", "自己也关注的其他艺人，具体语气看上下文"],
      ["饭籍／粉籍", "粉圈对粉丝身份的说法，不是正式资格证"],
      ["Leader／队长", "团队中的队长角色"],
      ["Vocal／Rapper／Dancer", "主唱、说唱、舞蹈相关角色的常见表述"],
      ["Center／C 位", "中心位置或中心角色，需结合具体语境"],
      ["Visual／门面", "与视觉形象有关的定位或粉丝称呼"],
      ["忙内／Maknae", "团体中年龄最小的成员"],
      ["Ace／全能", "对能力的评价，用法没有统一标准"],
      ["前辈／后辈", "常与出道先后等关系有关"],
      ["欧巴／Oppa", "韩语中女性称呼年长男性的一种方式"],
      ["欧尼／Unnie", "韩语中女性称呼年长女性的一种方式"],
      ["哥／Hyung", "韩语中男性称呼年长男性的一种方式"],
      ["努那／Noona", "韩语中男性称呼年长女性的一种方式"],
      ["OT＋人数", "常表达对某个人数阵容的支持，具体立场需看上下文"],
      ["回归／CB", "新作品及相关宣传活动"],
      ["出道／Debut", "正式开始艺人或团体活动"],
      ["回归期／活动期", "围绕一次作品展开集中宣传的时期"],
      ["Scheduler", "官方发布的宣传日程表"],
      ["Teaser", "预告，可能是图片、音频或视频"],
      ["Concept Photo", "概念照"],
      ["Tracklist", "曲目表"],
      ["Highlight Medley", "专辑片段试听"],
      ["主打／Title Track", "重点宣传的歌曲"],
      ["B-side", "主打之外的专辑收录曲"],
      ["先行曲", "完整作品推出前先发行的歌曲"],
      ["打歌", "上音乐节目等渠道宣传歌曲"],
      ["物料", "图片、视频、音频、文字等内容的统称"],
      ["直拍／Fancam", "聚焦成员或特定机位的视频"],
      ["饭拍", "粉丝拍摄的内容"],
      ["练习室", "常指完整展示编舞的练习视频"],
      ["花絮／Behind", "正式作品或活动背后的准备内容"],
      ["安可／Encore", "追加表演；也用于称呼部分打歌获胜后的表演"],
      ["饭撒／Fan Service", "面向粉丝的互动或表演行为"],
      ["音源", "在榜单讨论中通常指歌曲数字发行及使用成绩，要结合上下文"],
      ["音盘", "粉圈常用来讨论实体专辑"],
      ["初动", "通常指发行初期连续七天的销售成绩，须确认具体统计口径"],
      ["首日／首周／总销", "不同时间范围的销量，不能混着比较"],
      ["预售量", "需核对究竟指预订、订单还是其他口径"],
      ["出货量", "向销售渠道出库的数量，与终端零售不是同一个概念"],
      ["UL", "在指定时段内按平台规则去重的听众数"],
      ["空降", "新作品首次进入某榜时的成绩"],
      ["逆行", "发行一段时间后排名重新上升"],
      ["All Kill／AK", "达成某组榜单条件的称呼，不能理解为全球所有榜第一"],
      ["RAK／CAK／PAK", "不同 All Kill 称号，需按相应榜单体系的当期定义理解"],
      ["一位", "音乐节目某期评选的冠军"],
      ["预投／直播投票", "不同阶段的投票，不能默认通用"],
      ["本赏／大赏", "部分颁奖礼的奖项称呼，具体含义看该颁奖礼"],
      ["热趋／韩趋／世趋", "社交平台趋势相关说法，不等于音乐榜成绩"],
      ["官卡", "官方商品或活动体系中的卡片"],
      ["专卡", "常指专辑内附小卡"],
      ["特典／POB", "特定购买条件下的额外赠品，POB 常指预售特典"],
      ["LD／幸运抽", "Lucky Draw，按活动规则抽取"],
      ["随机／Random", "不能自行确定得到哪款"],
      ["Set／整套", "要进一步确认套装包含哪些版本"],
      ["通贩", "面向一般购买者的销售，具体资格仍看商品页"],
      ["初回／首批", "首次生产或发行批次相关表述，不等于销量「初动」"],
      ["代购", "由他人代为购买"],
      ["团购／拼团", "多人集中购买，需要确认组织者与费用规则"],
      ["开车／上车", "粉圈对组织或参加一批购买的口语说法"],
      ["补款／尾款／运补", "后续支付的商品或运输等费用，必须问清项目"],
      ["拆卡专／无卡专", "某些随机物已被取走的专辑"],
      ["裸专", "含义不统一，必须确认剩余内容"],
      ["饭制／自制", "粉丝制作，不等于官方商品"],
      ["复刻／复制卡", "复制品，不能直接当作官方原卡"],
      ["卡况／品相", "卡片保存状况"],
      ["捆／捆出", "卖家要求与其他物品一起购买"],
      ["跑单", "通常指承诺参与交易后未完成约定，具体争议看记录"],
      ["回血", "出售部分物品补回花费，不代表一定能回本"],
      ["MD／Merch", "周边商品"],
      ["FC／Fanclub", "粉丝俱乐部；看到「官方 FC」仍要核对实际身份与权益"],
      ["官咖／Fan Cafe", "官方或相关粉丝社区的常见说法"],
      ["泡泡／bubble", "常见订阅式沟通服务的称呼，权益按服务页面确认"],
      ["站子", "粉丝运营的资讯、翻译、摄影等账号或组织"],
      ["站姐／站哥", "常用于称呼拍摄、运营相关内容的粉丝，不代表公司人员"],
      ["大吧／个站", "团体或个人相关粉丝组织、账号的常见称呼"],
      ["中输", "部分讨论中指中国粉丝购买贡献或相关统计，需核对来源和口径"],
      ["拼盘", "多组艺人共同参与的演出"],
      ["预录", "正式播出前进行的录制"],
      ["候补", "等待空缺或追加资格，不等于已确定参加"],
      ["中签", "抽选入选，可能还要付款、核验或领票"],
      ["回流票", "重新释放的票源，具体成因和购买方式看票务公告"],
      ["中控", "演出中统一控制应援棒等灯光"],
      ["手幅", "常见纸质或布质应援物"],
      ["拉踩", "通过贬低别人抬高自己喜欢的对象"],
      ["控评", "有组织地影响评论区呈现的粉丝活动"],
      ["反黑", "粉丝对澄清、举报攻击性或不实内容等活动的称呼"],
      ["私生", "通常指严重侵犯艺人私人空间、行程和生活边界的行为者"],
      ["开盒", "搜集、泄露他人私人信息的行为"],
      ["饼／画饼／溜粉", "关于潜在机会、未兑现承诺等的粉圈说法，不能直接当正式消息"]
    ]
  },
  { t:"给自己安排一个轻松的第一个月", s:"不必按时交作业"
    , p:[
      "下面是一份可调整的入门安排，不需要按时「交作业」：",
      "如果预算是零元，可以一直停留在免费听歌、看官方公开内容、交流作品的方式上。",
      "如果有预算，可以先给自己设定一个包含运费、订阅和临时消费的总上限。看到随机赠品、限时销售或抽选活动时，先回到这个上限，再决定是否购买。",
      "时间也可以有上限：保留真正有用的通知，集中查看资讯，允许自己漏掉直播和更新。没有必要把多年物料在几周内补完。"
    ]
    , l:[
      ["第一周", "找到一个感兴趣的艺人，听几首歌和一张专辑", "知道自己喜欢什么"],
      ["第二周", "看完整舞台、采访或综艺，整理官方入口", "能区分成员及信息来源"],
      ["第三周", "跟一次新发行，理解预告、上线、宣传的关系", "能看懂回归日程"],
      ["第四周", "按兴趣尝试一次免费投票，或研究一件商品、一场演出", "能独立核对规则和总费用"]
    ]
  },
  { t:"遇到一次新回归，把整套知识用起来", s:"每一项都可以跳过"
    , p:[
      "假设你喜欢的组合宣布了一张新专辑，你可以这样走一遍：从官方公告确认发行名、时间和时区；想听歌就选择自己可用的平台，发行后听完整作品；想看舞台就关注官方视频和节目发布；想买一张就先定总预算，再核对版本、CD、赠品和售后；想支持某个榜就查清该榜采用什么数据；想投票就确认具体活动、候选、时间和票的用途；想抽签售就单独检查指定商品、申请和身份要求；想看演出就另外核对会籍、登记、售票、证件和出行。",
      "其中任何一项超出兴趣、精力或预算，都可以跳过。",
      "你会逐渐形成自己的追星方式：喜欢哪些声音、愿意看哪些内容、愿意为什么花钱、哪些活动值得出门。掌握这些判断，比把所有黑话和任务都记住更重要。"
    ]
    , acts:[["future", "去看未来的回归"], ["home", "回到首页今日概览"]]
  }
];

function guideHTML(){
  var h = '<div class="guide">'
    + '<div class="ghead"><h2>从头开始</h2><p>没追过 K-POP 也能看懂。看完这一页，你就知道「回归」是什么、该看什么、先点哪里。</p></div>';
  for(var i = 0; i < GUIDE.length; i++){
    var g = GUIDE[i];
    h += '<section class="gsec">'
       +   '<h3>' + esc(g.t) + '</h3>'
       +   (g.s ? '<div class="gsub">' + esc(g.s) + '</div>' : '');
    for(var j = 0; j < (g.p || []).length; j++){
      h += '<p class="gp">' + esc(g.p[j]) + '</p>';
    }
    if(g.l && g.l.length){
      h += '<ul class="gl">';
      for(var k = 0; k < g.l.length; k++){
        var row = g.l[k];
        /* 宝典里两种表格：两列（术语 → 含义）、三列（名称 → 说明 → 注意/误解） */
        h += '<li' + (row.length > 2 ? ' class="c3"' : '') + '>'
           + '<b>' + esc(row[0]) + '</b>'
           + '<span>' + esc(row[1] || "") + '</span>'
           + (row.length > 2 ? '<span>' + esc(row[2] || "") + '</span>' : '')
           + '</li>';
      }
      h += '</ul>';
    }
    if(g.acts){
      h += '<div class="gacts">';
      for(var a = 0; a < g.acts.length; a++){
        h += '<button class="btn gjump" data-jump="' + esc(g.acts[a][0]) + '">' + esc(g.acts[a][1]) + '</button>';
      }
      h += '</div>';
    }
    h += '</section>';
  }
  h += '</div>';
  return h;
}

/* ============================ 诉说（反馈 / 树洞） ============================
   纯静态站没有后端，所以走 mailto：点「发送」会打开本机邮件应用，
   内容已经填好。没有邮件应用的人可以点「复制」，自己粘到邮件里发。 */
var TELL_KINDS = ["想说的话", "网站报错", "内容纠错", "功能建议"];
function tellHTML(){
  var h = '<div class="tell">'
    + '<h3>诉说</h3>'
    + '<div class="gsub">这里是一个可以说话的地方。发现日期错了、页面坏了、想要某个功能，'
    + '或者只是今天有点想找个人说说——都可以写下来发给我。我都会看。</div>'
    + '<div class="chips tellchips">';
  for(var i = 0; i < TELL_KINDS.length; i++){
    h += '<button class="chip' + (S.tellKind === TELL_KINDS[i] ? ' on' : '') + '"'
       + ' data-tellkind="' + esc(TELL_KINDS[i]) + '">' + esc(TELL_KINDS[i]) + '</button>';
  }
  h += '</div>'
    + '<textarea id="tellText" class="tellta" placeholder="'
    + (S.tellKind === "网站报错" ? '哪个页面、点了什么、看到了什么异常情况…'
       : S.tellKind === "内容纠错" ? '哪个团体 / 专辑、哪里不对、正确的是什么…'
       : S.tellKind === "功能建议" ? '你希望这个站能多做一件什么事…'
       : '想说什么都行，我会当成树洞听完。不用署名。')
    + '">' + esc(S.tellText || "") + '</textarea>'
    + '<div class="tellfoot">'
    +   '<button class="btn pri" id="tellSend">发送到我邮箱</button>'
    +   '<button class="btn" id="tellCopy">复制内容</button>'
    + '</div></div>';
  return h;
}
function tellMail(){
  var subj = "【知未】" + S.tellKind;
  var body = (S.tellText || "")
    + "\n\n———\n页面：" + location.href
    + "\n时间：" + new Date().toLocaleString("zh-CN")
    + "\n（这行以下是自动带的，方便我定位问题）";
  return "mailto:" + REPORT_MAIL
       + "?subject=" + encodeURIComponent(subj)
       + "&body=" + encodeURIComponent(body);
}
function secHTML(title, list){
  if(!list.length) return "";
  return '<div class="sec-h"><h2>'+esc(title)+'</h2><span class="c">'+list.length+'</span>'
       + '<span class="line"></span></div>' + gridHTML(list);
}

/* ============================ 详情页 ============================ */
/* 反馈邮箱：换邮箱只改这一行。社区功能先拿这个入口试水，
   看看有没有人真的愿意反馈，有人再考虑上 Giscus / Twikoo。 */
var REPORT_MAIL = "139567293@qq.com";
function reportMail(r){
  var subj = "【知未】信息有误：" + (r.artist || "") + " - " + (r.title || "");
  var body = "页面：" + location.href + "\n专辑：" + (r.artist||"") + " - " + (r.title||"")
           + "（" + (r.date||"") + "）\n哪里不对：\n正确信息应该是：\n";
  return "mailto:" + REPORT_MAIL
       + "?subject=" + encodeURIComponent(subj)
       + "&body=" + encodeURIComponent(body);
}
function srcLabel(r){
  var s = r.source || "";
  if(s==="apple")   return "Apple Music";
  if(s==="netease") return "网易云音乐";
  if(s==="kpopping")return "kpopping 日程";
  if(s==="kpopcal") return "kpopcal";
  return "公开音乐资料";
}
function detailHTML(r){
  var dn = dispName(r.artist);
  var a = ART[r.artist] || {};
  var others = ALL.filter(function(x){ return x.artist===r.artist && x.id!==r.id; })
                  .sort(function(p,q){ return (q.date||"").localeCompare(p.date||""); })
                  .slice(0, 12);

  var h = '<div class="backbar"><button id="backBtn">‹ 返回</button>'
        + '<span style="font-size:12.5px;color:var(--sub)">专辑详情</span></div>';

  h += '<div class="dhero">'
    +  '<div class="art"><div class="ph">' + ico('note',22) + '</div>'
    +    imgTag(r, 'loading="lazy"')
    +  '</div>'
    +  '<div class="dinfo">'
    +    '<div class="dtitle">'+esc(r.title)+'</div>'
    +    '<div class="dar">'+heartHTML(r.artist, 20)
    +      '<span>'+esc(dn.zh)+'</span>'
    +      (dn.en ? '<span class="en">'+esc(dn.en)+'</span>' : '')
    +    '</div>'
    +    '<div class="dmeta">'
    +      '<b>'+esc(fmtDate(r.date))+'</b>'
    +      (r._tn ? '<span class="sep">·</span><span>'+r._tn+' 首歌曲</span>' : '')
    +      (r._dur ? '<span class="sep">·</span><span>'+esc(fmtDur(r._dur))+'</span>' : '')
    +      (typeLabel(r) ? '<span class="sep">·</span><span class="tag">'+esc(typeLabel(r))+'</span>' : '')
    +      (r._isNew ? '<span class="tag s">NEW</span>' : '')
    +    '</div>';

  var facts = [];
  var agn = a.parent || a.agency || r._agency;
  if(agn) facts.push("经纪公司：" + agn);
  if(a.fandom) facts.push("粉丝名：" + a.fandom);
  if(a.debut_year) facts.push("出道年：" + a.debut_year + " 年");
  if(r.copyright) facts.push("版权方：" + r.copyright);
  if(facts.length){
    h += '<div class="ddesc"><span class="lb">专辑信息</span>' + esc(facts.join("　·　")) + '</div>';
  }

  /* 官方 MV 只在首页「热门 MV」那一块用（用户拍板：详情页不挂 MV 入口）。
     以前这里按「同艺人 + 标题带专辑名」猜一个，命中率低还常常张冠李戴，删掉。 */

  h += '<div class="dact">'
    +  '<button class="btn" id="favDetail" style="padding:10px 18px;border-radius:11px;font-size:13px">'
    +    (isFav(r.id) ? ico('star',14,true)+' 已收藏' : ico('star',14)+' 收藏') + '</button>'
    +  '<button class="btn" id="reportBtn"'
    +    ' style="padding:10px 16px;border-radius:11px;font-size:13px">信息有误？告诉我们</button>'
    +  '<span class="dsrc">数据来源：' + esc(srcLabel(r)) + '</span>'
    + '</div>';

  h += '</div></div>';

  /* 曲目 */
  if(r._tracks.length){
    h += '<div class="dsec"><div class="hd">曲目列表<span class="c">'+r._tracks.length+' 首</span>'
       + '<span style="font-size:11.5px;color:var(--sub);font-weight:600;margin-left:auto">'
       + '点击歌曲查看详情</span></div>';
    r._tracks.forEach(function(t, i){
      var no = (t.no || (i+1));
      h += '<div class="trk" data-trk="'+i+'">'
        +  '<span class="no">'+no+'</span>'
        +  '<span class="nm">'+esc(t.n || "—")+'</span>'
        +  '<span class="du">'+esc(fmtDurShort(t.ms))+'</span>'
        +  '<span class="cv">▾</span>'
        + '</div>'
        + '<div class="trkext" id="ext'+i+'">'
        +  '<div class="extgrid">'
        +   '<div class="exi"><span class="k">时长</span><span class="v">'+esc(fmtDurShort(t.ms)||"—")+'</span></div>'
        +   '<div class="exi"><span class="k">曲序</span><span class="v">'
        +     (t.disc>1 ? ('Disc '+t.disc+' · 第 '+no+' 首') : ('第 '+no+' 首'))+'</span></div>'
        +  '</div>'
        + '</div>';
    });
    h += '</div>';
  } else {
    h += '<div class="dsec"><div class="hd">曲目列表</div>'
       + '<div style="padding:22px 18px;color:var(--sub);font-size:13px">'
       + '这张专辑的曲目暂未收录。通常是还没发行——'
       + '未来的专辑要先等上架，各平台才会给出曲目。'
       + '</div></div>';
  }

  /* 更多作品 */
  if(others.length){
    h += '<div class="dsec"><div class="hd">更多 '+esc(dn.zh)+' 的作品</div>'
       + '<div class="morewrap">';
    others.forEach(function(o){
      h += '<div class="more" data-open="'+esc(o.id)+'">'
        +  '<div class="im">'+(o._img ? '<img loading="lazy" src="'+esc(o._img)+'" alt="">' : '')+'</div>'
        +  '<div class="t">'+esc(o.title)+'</div>'
        +  '<div class="y">'+esc((o.date||"").slice(0,4))+'</div>'
        + '</div>';
    });
    h += '</div></div>';
  }
  return h;
}

/* ============================ 渲染 ============================ */
/* 顶部「今天 · 打歌节目」条：默认只显示今天，点「本周」展开整周时间表。
   首页改版（P0）会直接复用这一段。 */
/* 打歌节目条在首页和「更多」页各有一份。传 id 只刷那一个，
   不传则两个都刷——点开关时必须都刷，否则点首页的开关会去刷新日历页那份，看起来像没反应。 */
var SHOW_BOXES = ["homeShows", "showsBar"];
function renderShows(boxId){
  if(!boxId){
    for(var i = 0; i < SHOW_BOXES.length; i++) renderShows(SHOW_BOXES[i]);
    return;
  }
  var box = $(boxId); if(!box) return;
  var today = TODAY.getDay(), t = showsOn(today), head;

  if(t.length){
    head = t.map(function(s){
      return '<b>'+esc(s.zh)+'</b> <span>'+s.kst+' KST</span> <i>北京 '+kst2cst(s.kst)+'</i>';
    }).join(" · ");
  } else {
    var nx = showsOn((today+1) % 7);
    head = '<span class="shnone">今天没有打歌节目</span>'
         + (nx.length ? ' · 明天有 <b>'+esc(nx[0].zh)+'</b>' : '');
  }

  var rows = [1,2,3,4,5,6,0].map(function(w){
    var ss = showsOn(w);
    var nm = ss.length
      ? ss.map(function(s){ return esc(s.zh)+' <em>'+s.kst+'</em>'; }).join("、")
      : '<span class="shnone">—</span>';
    return '<div class="shrow'+(w===today ? ' today' : '')+'">'
         +   '<span class="shw">'+WK[w]+'</span>'
         +   '<span class="shn">'+nm+'</span>'
         +   '<span class="shc">'+(ss.length ? esc(ss[0].ch) : '')+'</span>'
         + '</div>';
  }).join("");

  box.innerHTML =
      '<div class="shhead">'
    +   '<span class="shic">'+ico('tv',15)+'</span>'
    +   '<span class="shtitle">今天 · 打歌节目</span>'
    +   '<span class="shnow">'+head+'</span>'
    +   '<button class="shmore" data-showtoggle>'+(S.showWeek ? '收起 ▴' : '本周 ▾')+'</button>'
    + '</div>'
    + '<div class="shweek" style="'+(S.showWeek ? '' : 'display:none')+'">'+rows
    +   '<div class="shnote">播出时间为韩国时间（KST），中国时间比韩国晚 1 小时；'
    +   '遇节假日或特别节目电视台可能临时调整。</div>'
    + '</div>';
}

/* ============================ 首页 ============================ */
/* 首页是默认页：今天发行 / 今天生日 / 打歌节目 / 未来 7 天倒计时。
   点「查看完整日历」进原来的 5 个 tab 界面。 */
function homeSec(title, sub, body){
  return '<section class="hsec">'
       +   '<div class="hsec-h"><h2>'+esc(title)+'</h2>'
       +     (sub ? '<span class="hs">'+esc(sub)+'</span>' : '')
       +   '</div>'
       +   body
       + '</section>';
}
function miniHTML(r){
  var dn = dispName(r.artist);
  return '<div class="mini'+(isBias(r.artist)?' bias':'')+'" data-open="'+esc(r.id)+'">'
    + '<div class="mcov"><div class="ph">' + ico('note',22) + '</div>'
    +   imgTag(r, 'loading="lazy"')
    +   ddayHTML(r)
    + '</div>'
    + '<div class="mt">'+esc(dn.zh)+'</div>'
    + '<div class="ms">'+esc(r.title)+'</div>'
    + '</div>';
}
function renderHome(){
  var box = $("homeView"); if(!box) return;

  var todayRel = ALL.filter(function(r){ return r.date === TODAY_S; })
                    .sort(function(a,b){ return (a.date||"").localeCompare(b.date||""); });
  var soon = ALL.filter(function(r){ return r._dd >= 0 && r._dd <= 7; })
                .sort(function(a,b){ return a._dd - b._dd; });
  var bds = birthdaysToday();
  var tt = showsOn(TODAY.getDay());

  /* 欢迎区：大字「知未」+ 一句话概览，右侧统计卡 */
  var bits = [];
  if(todayRel.length) bits.push('<b>'+todayRel.length+'</b> 张新发行');
  if(bds.length)      bits.push('<b>'+bds.length+'</b> 位艺人过生日');
  if(tt.length)       bits.push('今晚有 <b>'+esc(tt[0].zh)+'</b>');
  var h = '<div class="hero">'
    + '<div class="heroL">'
    +   '<div class="wel">欢迎来到</div>'
    +   '<div class="bigname">知未</div>'
    +   '<div class="hhd"><span class="hmd">'+(TODAY.getMonth()+1)+' 月 '+TODAY.getDate()+' 日</span>'
    +     '<span class="hwk">'+WK[TODAY.getDay()]+'</span></div>'
    +   '<div class="hsum">' + (bits.length ? bits.join(" · ") : '今天没有新发行，看看下面的回归倒计时') + '</div>'
    + '</div>'
    + '<div class="heroR" id="hstats"></div>'
    + '</div>';

  /* 今天发行 + 今日生日 + 随心歌单：左边内容、右边歌单，把空位填上 */
  h += '<div class="hduo"><div class="hduoL">';
  h += homeSec("今天发行", todayRel.length ? "共 "+todayRel.length+" 张" : "",
        todayRel.length ? '<div class="minibar">'+todayRel.map(miniHTML).join("")+'</div>'
                        : '<div class="hempty">今天没有发行安排</div>');

  /* 未来 7 天倒计时 */
  h += homeSec("未来 7 天回归", soon.length ? "共 "+soon.length+" 张" : "",
        soon.length ? '<div class="minibar">'+soon.slice(0,12).map(miniHTML).join("")+'</div>'
                    : '<div class="hempty">未来 7 天没有回归安排</div>');

  /* 今日生日：默认 5 位，多了点「展开」 */
  h += homeSec("今日生日", bds.length ? "共 "+bds.length+" 位" : "",
        bds.length ? bdayListHTML(bds) : '<div class="hempty">今天没有收录到艺人生日</div>');
  h += '</div>' + djHTML() + '</div>';

  /* 热门 MV：官方账号发布，按播放量排序（本月 → 三个月 → 一年 → 历史） */
  var hot = mvHot(), mm = hot.list;
  /* 副标题不写了：播放量排序本来就看得出来，字多了反而啰嗦（用户拍板删） */
  h += homeSec("热门 MV", "",
        mm.length
          ? '<div class="mvbar">' + mm.map(function(m){
              return '<a class="mvmini" href="'+mvURL(m)+'" target="_blank" rel="noopener nofollow">'
                + '<span class="mvcov">'
                +   '<div class="ph">' + ico('note',20)
                +     '<em>' + esc(m.u || m.a || "") + '</em></div>'  /* 图没抓到时显示 UP 主名，不留空框 */
                +   mvImgTag(m)
                +   '<span class="mvplay">▶ '+fmtPlay(m.p)+'</span>'
                + '</span>'
                + '<span class="mvtt">'+esc(m.t)+'</span>'
                + '<span class="mvau">'+esc(m.u)+'</span>'
                + '</a>';
            }).join("") + '</div>'
          : '<div class="hempty">近一个月还没有收录到官方 MV</div>');

  /* 打歌节目（复用列表页那一套） */
  h += homeSec("打歌节目", "韩国时间 KST",
        '<div class="showsbar" id="homeShows"></div>');

  h += '<div class="hfoot">'
    + '<button class="btn pri" id="toCal">查看完整日历</button>'
    + '<button class="btn pri" id="subCal">订阅到手机日历</button>'
    + '</div>';

  box.innerHTML = h;
  renderShows("homeShows");
  renderStats();
}

/* 今日生日：默认只摆 5 位，多了给一个「展开」，别占满整屏 */
function bdayListHTML(bds){
  var lim = 4;   /* 首屏只摆 4 位，多了点「展开」 */
  var show = S.bdMore ? bds.length : Math.min(lim, bds.length);
  var h = '<div class="bdaylist">' + bds.slice(0, show).map(function(m){
      var ag = ageOf(m.b);
      return '<div class="bday'+(isBias(m.g)||isBias(m.g2)?' bias':'')+'">'
        + '<span class="bav">'+ico('cake',15)+'</span>'
        + '<span class="bname">'+esc(m.n)+'</span>'
        + '<span class="bgrp">'+heartHTML(m.g)+esc(plainName(m.g))
        +   (m.g2 ? ' · '+esc(plainName(m.g2)) : '')+'</span>'
        + (ag !== null ? '<span class="bage">'+ag+' 岁</span>' : '')
        + '</div>';
    }).join("") + '</div>';
  if(bds.length > lim){
    h += '<button class="morebtn" id="bdMore">'
      + (S.bdMore ? '收起' : '还有 ' + (bds.length - lim) + ' 位 · 展开')
      + '</button>';
  }
  return h;
}

/* 随心歌单：随机挑 4 张已发行的专辑。随机结果存 S.djList，
   翻页 / 切页签都不会变，点「换一批」才重新抽 —— 不然每动一下就换一批，很吵 */
function djPick(){
  /* 只抽已发行的（_dd <= 0 = 今天或更早）。还没发行的不进歌单——
     点进去只能看个空壳，还以为站坏了。宁可少给几张也不掺未发行的 */
  var pool = ALL.filter(function(r){ return r._img && r._dd <= 0; });
  var out = [], used = {}, guard = 0;
  while(out.length < 4 && guard++ < 80){
    var r = pool[Math.floor(Math.random() * pool.length)];
    if(!r || used[r.id]) continue;
    used[r.id] = 1; out.push(r);
  }
  return out;
}
function djHTML(){
  if(!S.djList || !S.djList.length) S.djList = djPick();
  if(!S.djList.length){
    return '<aside class="dj"><div class="djtop"><h3>随心歌单</h3></div>'
         + '<div class="djsub">还没有已发行的专辑可以抽</div></aside>';
  }
  var h = '<aside class="dj">'
    + '<div class="djtop"><h3>随心歌单</h3>'
    +   '<button class="btn" id="djMore">换一批</button></div>'
    + '<div class="djsub">不知道听什么？听天由命</div>'
    + '<div class="djgrid">';
  for(var i = 0; i < S.djList.length; i++){
    var r = S.djList[i], dn = dispName(r.artist);
    h += '<button class="djc" data-open="'+esc(r.id)+'">'
      +  '<span class="djcov">'
      +    (r._img ? '<img loading="lazy" src="'+esc(r._img)+'" alt="" onerror="this.style.display=\'none\'">' : '')
      +  '</span>'
      +  '<span class="djt">'+esc(r.title)+'</span>'
      +  '<span class="dja">'+esc(dn.zh || r.artist)+'</span>'
      +  '</button>';
  }
  h += '</div></aside>';
  return h;
}

function renderStats(){
  var el = $("hstats"); if(!el) return;
  var up = ALL.filter(function(r){ return r._dd>=0 && r._dd<=30; });
  var bi = up.filter(function(r){ return isBias(r.artist); });
  var nw = ALL.filter(function(r){ return r._isNew && r._dd>=0; });
  var past = ALL.filter(function(r){ return r._dd<0; });
  el.innerHTML =
      '<div class="hstat"><div class="v">'+up.length+'</div><div class="k">未来 30 天回归</div></div>'
    + '<div class="hstat'+(bi.length?' hl':'')+'"><div class="v">'+bi.length+'</div><div class="k">本命即将回归</div></div>'
    + '<div class="hstat"><div class="v">'+nw.length+'</div><div class="k">新人待发</div></div>'
    + '<div class="hstat"><div class="v">'+past.length+'</div><div class="k">近一年已收录</div></div>'
    + '<div class="hstat"><div class="v">'+Object.keys(ART).length+'</div><div class="k">追踪艺人</div></div>';
}
function renderBiasBox(){
  $("biasList").innerHTML = bias.length
    ? bias.map(function(n){
        var a = ART[n];
        return '<span class="btag">&#10084; '+esc(plainName(n))
             + (a&&a.fandom ? ' <span style="opacity:.6;font-weight:600">'+esc(a.fandom)+'</span>' : '')
             + '<button data-rmbias="'+esc(n)+'" title="移除">×</button></span>';
      }).join("")
    : '<span style="font-size:12.5px;color:var(--sub)">还没有添加本命。</span>';

  var cnt = {};
  ALL.forEach(function(r){ if(r.artist) cnt[r.artist] = (cnt[r.artist]||0)+1; });
  var top = Object.keys(cnt).filter(function(n){ return bias.indexOf(n)<0; })
    .sort(function(a,b){ return cnt[b]-cnt[a]; }).slice(0, 16);
  $("biasSugg").innerHTML = top.length
    ? '<div style="width:100%;font-size:11.5px;color:var(--sub);font-weight:700">常见艺人，点击添加：</div>'
      + top.map(function(n){ return '<button class="chip" data-addbias="'+esc(n)+'">+ '+esc(plainName(n))+'</button>'; }).join("")
    : "";
}
/* 过去模块分页：历史回填后全库 4700+ 张，一次全塞 DOM 手机直接卡死。
   改成每页 PAGE_SIZE 张 + 页码，要哪页渲染哪页。
   筛选条件一变就回第 1 页（用条件签名判断，不用挨个改事件处理器）。 */
var PAGE_SIZE = 30, page = 1, listSig = null;
function listSignature(){
  return [S.tab, S.q, S.type, S.kind, S.agency, S.onlyFav, S.onlyBias,
          S.sort, S.range && S.range.label].join("|");
}

/* 页码条：最多 7 个数字，两端用省略号，首页末页常驻 */
function pageList(cur, total){
  var out = [], MAX = 7;
  if(total <= MAX){
    for(var i = 1; i <= total; i++) out.push(i);
    return out;
  }
  out.push(1);
  var s = Math.max(2, cur - 2), e = Math.min(total - 1, cur + 2);
  if(s > 2) out.push(0);                       // 0 = 省略号
  for(var i = s; i <= e; i++) out.push(i);
  if(e < total - 1) out.push(0);
  out.push(total);
  return out;
}
function pagerHTML(cur, total, n){
  var h = '<div class="pager">'
    + '<button class="pgb"' + (cur === 1 ? ' disabled' : ' data-page="' + (cur - 1) + '"')
    + '>上一页</button>';
  pageList(cur, total).forEach(function(p){
    h += p === 0 ? '<span class="pgd">…</span>'
       : '<button class="pgb' + (p === cur ? ' on' : '') + '" data-page="' + p + '">' + p + '</button>';
  });
  h += '<button class="pgb"' + (cur === total ? ' disabled' : ' data-page="' + (cur + 1) + '"')
    + '>下一页</button>'
    + '<span class="pgc">共 ' + n + ' 张 · ' + total + ' 页</span></div>';
  return h;
}

function renderList(){
  renderBiasBox();
  $("biasBox").style.display = (S.tab==="mine" && S.mine==="bias" || S.showBiasMgr) ? "" : "none";
  $("dateLabel").textContent = S.range.label;
  $("dateBtn").classList.toggle("on", S.range.mode === "custom");

  /* 控制条显隐：未来有三档子选项，过去有完整筛选，我的有收藏/本命切换 */
  var isFuture = (S.tab==="future"), isPast = (S.tab==="past");
  var isMine = (S.tab==="mine"), isMore = (S.tab==="more"), isGuide = (S.tab==="guide");
  $("showsBar").style.display = isMore ? "" : "none";
  if(isMore) renderShows("showsBar");
  $("upBar").classList.toggle("on", isFuture);
  $("mineBar").classList.toggle("on", isMine);
  $("filters").style.display = isPast ? "" : "none";
  if(isGuide){                       /* 指南页不需要任何筛选控件 */
    $("content").innerHTML = guideHTML();
    return;
  }
  $("biasBox").style.display = (isMine && S.mine==="bias") || S.showBiasMgr ? "" : "none";

  if(isFuture){
    document.querySelectorAll("#upBar [data-up]").forEach(function(b){
      b.classList.toggle("on", b.getAttribute("data-up") === S.frange);
    });
  }
  if(isMine){
    document.querySelectorAll("#mineBar [data-mine]").forEach(function(b){
      b.classList.toggle("on", b.getAttribute("data-mine") === S.mine);
    });
  }

  var html = "";
  if(isFuture){
    var R = activeRange();
    /* 订阅入口放在这里：日历订阅是这个页最该做的事，只在页脚写文件地址太容易被错过。
       注意存进单独变量 —— 下面 html 会被整体重新赋值，直接 += 会被冲掉。 */
    var subBar = '<div class="subrow">'
          +   '<span>' + ico('cal',15) + '把这个日历同步到手机，回归日每天自动更新</span>'
          +   '<button class="btn" id="subCal2">订阅到手机日历</button>'
          + '</div>';
    var ul = applyFilters(ALL).filter(function(r){ return r._dd >= -0.5; })
               .sort(function(a,b){ return a._dd - b._dd; });
    if(S.frange === "month" || S.frange === "nmonth"){
      var nU = ul.filter(function(r){ return r._dd >= 0; }).length;
      html = ul.length ? gridHTML(ul)
        : '<div class="empty"><div class="e">' + ico('head',26) + '</div><h3>' + esc(R.label) + '没有回归记录</h3>'
          + '<p>数据每天自动更新</p></div>';
      html = '<div class="mohead"><b>' + esc(R.label) + '</b><span>共 ' + ul.length
           + ' 张 · 其中 ' + nU + ' 张还没发行</span></div>' + html;
    } else {
      html = ul.length
        ? '<div class="sec-h"><h2>即将回归 · 7 天</h2><span class="c">' + ul.length
          + '</span><span class="line"></span></div>' + gridHTML(ul)
        : '<div class="empty"><div class="e">' + ico('head',26) + '</div><h3>未来 7 天没有回归</h3>'
          + '<p>换「本月」看看，或去「过去」翻历史</p></div>';
    }
    html = subBar + html;
  } else if(isPast){
    ensureYears();
    var sig = listSignature();
    if(sig !== listSig){ page = 1; listSig = sig; }
    var pl = applyFilters(ALL);
    var pages = Math.max(1, Math.ceil(pl.length / PAGE_SIZE));
    if(page > pages) page = pages;
    if(page < 1) page = 1;
    var from = (page - 1) * PAGE_SIZE;
    html = gridHTML(pl.slice(from, from + PAGE_SIZE))
         + (pages > 1 ? pagerHTML(page, pages, pl.length) : "");
  } else if(isMine && S.mine === "fav"){
    ensureYears();                 /* 旧年份的收藏也要能显示出来 */
    var fl = ALL.filter(function(r){ return isFav(r.id); });
    var fu = fl.filter(function(r){ return r._dd>=0; }).sort(function(a,b){ return a._dd-b._dd; });
    var fp = fl.filter(function(r){ return r._dd<0; });
    html = fl.length ? secHTML("收藏 · 即将发行", fu) + secHTML("收藏 · 已发行", fp)
      : '<div class="empty"><div class="e">' + ico('star',24) + '</div><h3>还没有收藏</h3><p>在卡片右上角点星标即可收藏</p></div>';
  } else if(isMore){
    /* 打歌节目时间表在上方（showsBar），下面是「诉说」窗口 */
    html = tellHTML();
  } else if(isMine && S.mine === "bias"){
    if(!bias.length){
      html = '<div class="empty"><div class="e">' + ico('heart',24) + '</div><h3>还没有设置本命</h3>'
           + '<p>在上方「本命团体管理」里添加，或点卡片上的爱心</p></div>';
    } else {
      var bl = ALL.filter(function(r){ return isBias(r.artist); });
      var bu = bl.filter(function(r){ return r._dd>=0; }).sort(function(a,b){ return a._dd-b._dd; });
      var bp = bl.filter(function(r){ return r._dd<0; });
      html = secHTML("本命 · 即将发行", bu) + secHTML("本命 · 已发行", bp);
      if(!html) html = '<div class="empty"><div class="e">' + ico('heart',24) + '</div><h3>本命暂无记录</h3><p>数据每天更新</p></div>';
    }
  }
  $("content").innerHTML = html;
  $("cFav").classList.toggle("on", S.onlyFav);
  $("cBias").classList.toggle("on", S.onlyBias);
  $("cReset").style.display = (S.q||S.type||S.kind||S.agency||S.onlyFav||S.onlyBias) ? "" : "none";
  $("qclr").classList.toggle("on", !!S.q);
}

/* ============================ 自定义下拉 ============================ */
/* 原生 <select> 展开后是浏览器画的下拉列表，CSS 管不到，跟页面风格对不上。
   这里把 #filters 里的 select 全部换成自绘面板：底层 select 保留（值同步、
   键盘可用），外观和弹出列表走我们自己的样式。 */
function closeAllSels(){
  document.querySelectorAll(".selpop.on").forEach(function(p){ p.classList.remove("on"); });
}
function initSelects(){
  document.querySelectorAll("#filters select").forEach(function(sel){
    if(sel.getAttribute("data-seldone")) return;
    sel.setAttribute("data-seldone", "1");

    var wrap = document.createElement("div");
    wrap.className = "selwrap";
    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(sel);
    sel.style.display = "none";

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "selbtn";
    var txt = document.createElement("span");
    txt.className = "seltxt";
    btn.appendChild(txt);
    var arw = document.createElement("span");
    arw.className = "selarw";
    btn.appendChild(arw);
    wrap.appendChild(btn);

    var pop = document.createElement("div");
    pop.className = "selpop";
    wrap.appendChild(pop);

    function sync(){
      var o = sel.options[sel.selectedIndex];
      txt.textContent = o ? o.text : (sel.getAttribute("placeholder") || "");
      /* 注意：状态类不能叫 empty —— 全局 .empty 是「列表为空」提示块的样式
         （padding:64px 20px），同名会把下拉框撑成 130px 的大方块。 */
      btn.classList.toggle("unsel", !sel.value && sel.selectedIndex <= 0
        && !!sel.options[0] && sel.options[0].value === "");
    }
    function fill(){
      pop.innerHTML = "";
      /* optgroup 渲染成分组标题（fKind 的 团体>男团/女团 就是靠它分级） */
      Array.prototype.forEach.call(sel.children, function(n){
        if(n.tagName === "OPTGROUP"){
          var hd = document.createElement("div");
          hd.className = "selgrp";
          hd.textContent = n.label;
          pop.appendChild(hd);
          Array.prototype.forEach.call(n.children, function(o){ addItem(o); });
        } else if(n.tagName === "OPTION"){
          addItem(n);
        }
      });
      function addItem(o){
        var b = document.createElement("button");
        b.type = "button";
        b.className = "selopt" + (o.selected ? " on" : "");
        b.setAttribute("data-selv", o.value);
        b.textContent = o.text;
        pop.appendChild(b);
      }
    }
    btn.addEventListener("click", function(e){
      e.stopPropagation();
      var open = pop.classList.contains("on");
      closeAllSels();
      if(!open){ fill(); pop.classList.add("on"); }
    });
    pop.addEventListener("click", function(e){
      var b = e.target.closest(".selopt");
      if(!b) return;
      sel.value = b.getAttribute("data-selv");
      sel.dispatchEvent(new Event("change"));
      sync();
      pop.classList.remove("on");
    });
    sync();
  });
}

/* 切页时给容器重放一次淡入（先摘 class 再强制重排，动画才会重新跑） */
function animIn(el){
  if(!el) return;
  el.classList.remove("rise");
  void el.offsetWidth;
  el.classList.add("rise");
}
function render(){
  /* 首页（默认页）与日历界面互斥；打开详情时让位 */
  var home = (S.view === "home" && !S.detailId);
  $("homeView").style.display = home ? "" : "none";
  if(home){
    $("listView").style.display = "none";
    $("detailView").style.display = "none";
    renderHome();
    animIn($("homeView"));
    window.scrollTo({top:0,behavior:"instant"});
    return;
  }
  if(S.detailId){
    $("listView").style.display = "none";
    $("detailView").style.display = "";
    var r = null;
    for(var i=0;i<ALL.length;i++){ if(ALL[i].id===S.detailId){ r=ALL[i]; break; } }
    if(!r){ S.detailId=null; render(); return; }
    $("detailView").innerHTML = detailHTML(r);
    animIn($("detailView"));
    window.scrollTo({top:0,behavior:"instant"});
  } else {
    $("listView").style.display = "";
    $("detailView").style.display = "none";
    renderList();
    animIn($("content"));
  }
}
/* 订阅日历：复制链接 + 各平台怎么用 */
function subscribeCalendar(){
  var u = (location.protocol === "file:" ? "https://mywooji.cn/" : location.origin + "/")
        + "zhiwei.ics";
  copyText(u);
  alert("订阅链接已复制：\n" + u + "\n\n怎么用：\n"
    + "iPhone：设置 → 日历 → 账户 → 添加订阅账户，粘贴链接\n"
    + "安卓：Google 日历 → 设置 → 添加日历 → 通过网址订阅\n"
    + "电脑：把链接加进系统日历或 Outlook 的网络日历\n\n"
    + "订阅后每天自动更新，不用再回来看。");
}

/* 打开详情时把专辑写进网址（#release=id），这样复制网址就能分享这张专辑；
   关掉时把地址还原回列表，浏览器前进/后退也能正常走。 */
function openDetail(id){
  S.detailId = id;
  var h = "#release=" + encodeURIComponent(id);
  if(location.hash !== h) history.pushState(null, "", h);
  render();
}
function closeDetail(){
  if(!S.detailId) return false;
  S.detailId = null;
  var h = S.view === "home" ? "#view=home" : "#tab=" + S.tab;
  if(location.hash !== h) history.pushState(null, "", h);
  return true;
}

/* ============================ 爱心动画 ============================ */
function burst(el){
  var glyphs = ["&#10084;","&#10084;","&#10084;","&#10084;","&#10084;","&#10084;"];
  for(var i=0;i<6;i++){
    var s = document.createElement("span");
    s.className = "spark";
    s.innerHTML = glyphs[i];
    var ang = (Math.PI*2/6)*i - Math.PI/2;
    s.style.setProperty("--dx", (Math.cos(ang)*26).toFixed(1)+"px");
    s.style.setProperty("--dy", (Math.sin(ang)*26).toFixed(1)+"px");
    s.style.left = "50%"; s.style.top = "50%";
    el.appendChild(s);
    (function(node){ setTimeout(function(){ if(node.parentNode) node.parentNode.removeChild(node); }, 750); })(s);
  }
}

/* ============================ 日历 ============================ */
var CAL = { y:0, m:0, from:null, to:null, picking:false, view:"day" };
function calInit(){
  CAL.y = TODAY.getFullYear(); CAL.m = TODAY.getMonth();
  CAL.from = null; CAL.to = null; CAL.picking = false; CAL.view = "day";
}
function monLastDay(y,m){ return new Date(y, m+1, 0).getDate(); }
function calCls(c){
  var cls = "cald";
  if(DATE_COUNT[c.date]) cls += " has";
  if(c.date === TODAY_S) cls += " today";
  var F = CAL.from, T = CAL.to;
  if(F && T){
    if(c.date > F && c.date < T) cls += " inr";
    if(c.date === F || c.date === T) cls += " sel";
  } else if(F && c.date === F) cls += " sel";
  return cls;
}
function calSelRange(kind){
  var y = CAL.y, m = CAL.m;
  if(kind === "month"){
    CAL.from = y+"-"+pad(m+1)+"-01";
    CAL.to   = y+"-"+pad(m+1)+"-"+pad(monLastDay(y,m));
    CAL.picking = false;
  } else if(kind === "year"){
    CAL.from = y+"-01-01"; CAL.to = y+"-12-31"; CAL.picking = false;
  } else {
    CAL.from = null; CAL.to = null; CAL.picking = false;
  }
  renderCal();
}
function renderCal(){
  var y = CAL.y, m = CAL.m;
  $("calMon").textContent = y + " 年 " + (m+1) + " 月";

  /* ---- 年 / 月快速跳转面板 ---- */
  var mv = (CAL.view === "month");
  $("calPick").classList.toggle("on", mv);
  $("calBody").style.display = mv ? "none" : "";
  if(mv){
    var mh = '<div class="pyh"><button data-caly="-1">‹</button><span>'+y+' 年</span>'
           + '<button data-caly="1">›</button></div>';
    for(var mi=0; mi<12; mi++){
      mh += '<button class="mc'+(mi===m?' on':'')+'" data-calmon="'+mi+'">'+(mi+1)+' 月</button>';
    }
    $("calPick").innerHTML = mh;
  }

  var first = new Date(y, m, 1);
  var startWd = first.getDay();
  var days = new Date(y, m+1, 0).getDate();
  var prevDays = new Date(y, m, 0).getDate();

  var cells = [];
  for(var i=startWd-1;i>=0;i--) cells.push({d: prevDays-i, out:true, date:null});
  for(var d=1; d<=days; d++){
    var ds = y+"-"+pad(m+1)+"-"+pad(d);
    cells.push({d:d, out:false, date:ds});
  }
  while(cells.length % 7 !== 0) cells.push({d: cells.length, out:true, date:null});

  var wd = ["日","一","二","三","四","五","六"];
  var grid = $("calGrid"), key = y + "-" + pad(m+1);
  var real = cells.filter(function(c){ return !c.out; });

  /* 同一个月内只改 class，不重建节点 —— 否则鼠标下的按钮被换掉，
     浏览器会把 click 的目标降级到 #calGrid，导致点了没反应 */
  if(grid.getAttribute("data-key") === key
     && grid.querySelectorAll("[data-day]").length === real.length){
    var bs = grid.querySelectorAll("[data-day]");
    for(var bi=0; bi<bs.length; bi++) bs[bi].className = calCls(real[bi]);
  } else {
    var h = wd.map(function(w){ return '<span class="wd">'+w+'</span>'; }).join("");
    cells.forEach(function(c){
      if(c.out){ h += '<button class="cald out" disabled>'+c.d+'</button>'; return; }
      h += '<button class="'+calCls(c)+'" data-day="'+c.date+'">'+c.d+'</button>';
    });
    grid.innerHTML = h;
    grid.setAttribute("data-key", key);
  }

  /* ---- 已选范围提示 + 确定按钮可用性 ---- */
  var F = CAL.from, T = CAL.to;
  if(F && T && F !== T)   $("calRng").innerHTML = '已选 <b>'+F+'</b> → <b>'+T+'</b>　共 '+daySpan(F,T)+' 天';
  else if(F)              $("calRng").innerHTML = '已选 <b>'+F+'</b>（单日）';
  else                    $("calRng").innerHTML = '点日期选范围，可跨月；点标题跳年/月';
  var ap = $("calApply");
  ap.style.opacity = F ? "" : ".4";
  ap.style.cursor  = F ? "" : "default";
}
function daySpan(a,b){
  var da = new Date(a+"T00:00:00"), db = new Date(b+"T00:00:00");
  return Math.round((db-da)/86400000) + 1;
}
function openCal(){
  var btn = $("dateBtn"), pop = $("calPop");
  if(CAL.y === 0) calInit();
  if(S.range.mode === "custom"){ CAL.from = S.range.from; CAL.to = S.range.to; }
  CAL.view = "day";
  renderCal();
  pop.classList.add("on");
  var rect = btn.getBoundingClientRect();
  var host = pop.parentNode.getBoundingClientRect();
  var w = pop.offsetWidth || 306;
  var left = rect.left - host.left;
  if(left + w > host.width) left = Math.max(0, host.width - w);
  pop.style.left = left + "px";
  /* 下方空间不够就翻到按钮上方，避免被视口截断 */
  var ph = pop.offsetHeight || 0;
  if(rect.bottom + ph + 14 > window.innerHeight && rect.top - ph - 12 > 0){
    pop.style.top = Math.max(4, rect.top - host.top - ph - 6) + "px";
  } else {
    pop.style.top = (rect.bottom - host.top + 6) + "px";
  }
  pop.scrollTop = 0;
}
function closeCal(){ $("calPop").classList.remove("on"); }
function syncTabs(){
  document.querySelectorAll(".tab").forEach(function(x){
    var v = x.getAttribute("data-view");
    var on = v ? (S.view === "home")
                : (S.view === "calendar" && x.getAttribute("data-tab") === S.tab);
    x.classList.toggle("on", on);
  });
}

/* ============================ 赞赏 ============================ */
/* 收款码：现在放的是占位图。把你的微信 / 支付宝收款码转成 base64 填进下面两行的
   引号里即可，填好后页面自动显示你自己的收款码（转 base64 这步可以让我帮你做）。 */
var PAY_QR = {
  wechat: "data:image/jpeg;base64,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",
  alipay: "data:image/jpeg;base64,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"
};
function SponShow(kind){
  var img = $("sponImg");
  if(img){ img.src = PAY_QR[kind] || PAY_QR.wechat; }
}
SponShow("wechat");

/* ============================ 事件 ============================ */
document.addEventListener("click", function(e){
  var t = e.target, el;

  /* 过去模块翻页：只渲染那一页，翻完滚回列表顶部 */
  var pg = t.closest("[data-page]");
  if(pg && !pg.hasAttribute("disabled")){
    page = parseInt(pg.getAttribute("data-page"), 10) || 1;
    render();
    var c = $("content");
    if(c) window.scrollTo({ top: c.offsetTop - 70, behavior: "smooth" });
    return;
  }

  /* 赞赏：开关面板 / 切换收款码 / 点面板外自动收起
     两个要点：
     1) 用 closest 判断，绝不在面板上写 stopPropagation——会掐断 document 级事件委托（踩过）。
     2) 整段做空值保护——这段代码在所有点击时都会执行，一旦报错，整个页面都会点不动。 */
  var sp = $("sponPop");
  if(sp){
    if(t.closest("#sponBtn")){ sp.classList.toggle("on"); return; }
    if((el = t.closest(".spontab"))){
      document.querySelectorAll(".spontab").forEach(function(x){ x.classList.toggle("on", x === el); });
      SponShow(el.getAttribute("data-pay"));
      return;
    }
    if(t.closest("#sponX")){ sp.classList.remove("on"); return; }
    if(sp.classList.contains("on") && !t.closest("#sponPop")){ sp.classList.remove("on"); }
  }

  /* 下载页开关 */

  /* 本命爱心 */
  if((el = t.closest("[data-heart]"))){
    e.stopPropagation();
    var art = el.getAttribute("data-heart");
    var i = bias.indexOf(art);
    if(i >= 0){ bias.splice(i,1); toast("已移出本命"); }
    else { bias.push(art); el.classList.add("pop"); burst(el); toast("已加入本命"); }
    LS.set("bias", bias);
    setTimeout(function(){ if(el && el.parentNode) el.classList.remove("pop"); }, 540);
    render();
    return;
  }
  /* 收藏 */
  if((el = t.closest("[data-fav]"))){
    e.stopPropagation();
    var id = el.getAttribute("data-fav");
    var j = favs.indexOf(id);
    if(j >= 0){ favs.splice(j,1); toast("已取消收藏"); } else { favs.push(id); toast("已收藏"); }
    LS.set("favs", favs); render(); return;
  }
  if(t.closest("[data-stop]")) return;   /* 外链放行 */

  /* 本命管理按钮 */
  if((el = t.closest("[data-rmbias]"))){ toggleBias(el.getAttribute("data-rmbias")); return; }
  if((el = t.closest("[data-addbias]"))){ addBias(el.getAttribute("data-addbias")); return; }
  /* 日历：点标题切换 年/月 面板 */
  if((el = t.closest("[data-calview]"))){
    CAL.view = (CAL.view === "month") ? "day" : "month"; renderCal(); return;
  }
  /* 日历：面板内切年份 */
  if((el = t.closest("[data-caly]"))){
    CAL.y += parseInt(el.getAttribute("data-caly"), 10); renderCal(); return;
  }
  /* 日历：选中某月并跳过去 */
  if((el = t.closest("[data-calmon]"))){
    CAL.m = parseInt(el.getAttribute("data-calmon"), 10);
    CAL.view = "day"; renderCal(); return;
  }
  /* 日历：整月 / 整年 / 清空 */
  if((el = t.closest("[data-calsel]"))){ calSelRange(el.getAttribute("data-calsel")); return; }
  if((el = t.closest("[data-day]"))){
    var ds = el.getAttribute("data-day");
    if(!CAL.picking || !CAL.from || (CAL.from && CAL.to)){
      CAL.from = ds; CAL.to = null; CAL.picking = true;
    } else {
      if(ds < CAL.from){ CAL.to = CAL.from; CAL.from = ds; } else { CAL.to = ds; }
      CAL.picking = false;
    }
    renderCal(); return;
  }
  /* 曲目展开 */
  if((el = t.closest("[data-trk]"))){
    var idx = el.getAttribute("data-trk");
    var ext = $("ext"+idx);
    if(ext){
      var open = ext.classList.contains("on");
      ext.classList.toggle("on", !open);
      el.classList.toggle("open", !open);
    }
    return;
  }
  /* 打开详情 */
  if((el = t.closest("[data-open]"))){
    openDetail(el.getAttribute("data-open"));
    return;
  }
  if(t.id === "backBtn"){ closeDetail(); syncTabs(); render(); return; }
  if(t.id === "bdMore"){ S.bdMore = !S.bdMore; render(); return; }
  if(t.id === "toCal"){ S.view = "calendar"; syncTabs(); render(); window.scrollTo({top:0,behavior:"smooth"}); return; }
  /* 订阅日历：首页和「未来」页两个按钮共用 */
  if(t.id === "subCal" || t.id === "subCal2"){ subscribeCalendar(); return; }
  /* 信息有误：不再走 mailto（弹出系统邮件或浏览器很突兀），
     改成跳到站内「诉说」窗口，并预填这张专辑的信息 */
  if(t.id === "reportBtn"){
    var rr = null;
    for(var i = 0; i < ALL.length; i++){ if(ALL[i].id === S.detailId){ rr = ALL[i]; break; } }
    closeDetail();
    S.view = "calendar"; S.tab = "more"; S.tellKind = "内容纠错";
    S.tellText = "专辑：" + ((rr && rr.artist) || "") + " - " + ((rr && rr.title) || "")
               + "（" + ((rr && rr.date) || "") + "）\n哪里不对：\n正确信息应该是：\n";
    syncTabs(); render();
    var ta = $("tellText");
    if(ta){ ta.scrollIntoView({behavior:"smooth", block:"center"}); ta.focus(); }
    return;
  }
  if(t.id === "brandHome"){ closeDetail(); S.view = "home"; syncTabs(); render(); return; }
  /* 收藏按钮（详情页） */
  if(t.id === "favDetail"){
    var cur = S.detailId; var k = favs.indexOf(cur);
    if(k>=0){ favs.splice(k,1); toast("已取消收藏"); } else { favs.push(cur); toast("已收藏"); }
    LS.set("favs", favs); render(); return;
  }
  /* 加载某个年份的发行数据 */
  if((el = t.closest("[data-year]"))){
    var y = el.getAttribute("data-year");
    loadYear(y, function(){ render(); });
    return;
  }
  /* 打歌节目：展开 / 收起本周时间表 */
  if((el = t.closest("[data-showtoggle]"))){
    S.showWeek = !S.showWeek; renderShows(); return;
  }
  /* 即将回归的 7 天 / 30 天切换 */
  if((el = t.closest("[data-up]"))){
    S.frange = el.getAttribute("data-up"); render(); return;
  }
  if((el = t.closest("[data-mine]"))){
    S.mine = el.getAttribute("data-mine"); render(); return;
  }
  /* 首页 tab */
  if((el = t.closest("[data-view]"))){
    S.view = "home"; S.detailId = null;
    syncTabs(); render(); window.scrollTo({top:0,behavior:"smooth"}); return;
  }
  /* 日历 tab */
  if((el = t.closest("[data-tab]"))){
    S.view = "calendar";
    S.tab = el.getAttribute("data-tab"); S.detailId = null;
    /* 「即将回归」「本月回归」不带筛选，各自用固定范围，
       所以这里的 S.range 只服务于「全部发布」。 */
    if(S.tab==="past" && S.range.kind==="f30" && S.range.mode==="quick"){
      S.range = rangePreset("p365");
    }
    syncTabs(); render(); window.scrollTo({top:0,behavior:"smooth"}); return;
  }
  /* 点击空白关日历与下拉 */
  if(!t.closest("#calPop") && !t.closest("#dateBtn")) closeCal();
  if(!t.closest(".selwrap")) closeAllSels();
});

/* 复制文本：优先用剪贴板接口，老浏览器退回 execCommand */
function copyText(s){
  var done = function(){ toast("已复制，粘贴到邮件里发给我就行"); };
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(s).then(done, fallback);
  } else { fallback(); }
  function fallback(){
    var ta = document.createElement("textarea");
    ta.value = s; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); }
    catch(e){ toast("复制失败，请手动选中文本复制"); }
    document.body.removeChild(ta);
  }
}

/* ---- 诉说：类别切换 / 草稿 / 发送 ---- */
document.addEventListener("click", function(e){
  var el, t = e.target;
  if(!t.closest) return;
  /* 随心歌单：换一批 */
  if(t.id === "djMore" || t.closest("#djMore")){
    S.djList = null; render(); return;
  }
  /* 指南里的跳转按钮：直接切到对应页签 */
  if((el = t.closest("[data-jump]"))){
    S.view = "calendar"; S.tab = el.getAttribute("data-jump");
    if(S.tab === "mine") S.mine = "bias";
    syncTabs(); render(); window.scrollTo({top:0,behavior:"smooth"}); return;
  }
  if((el = t.closest("[data-tellkind]"))){
    S.tellKind = el.getAttribute("data-tellkind"); render(); return;
  }
  if(t.id === "tellSend" || t.closest("#tellSend")){
    var txt = ($("tellText") || {}).value || "";
    if(!txt.trim()){ toast("先写点什么吧"); return; }
    S.tellText = txt;
    window.location.href = tellMail();
    toast("已唤起邮件应用，确认发送即可");
    return;
  }
  if(t.id === "tellCopy" || t.closest("#tellCopy")){
    var v = ($("tellText") || {}).value || "";
    if(!v.trim()){ toast("先写点什么吧"); return; }
    copyText(v);
    return;
  }
});
/* textarea 直接绑不上（每次 render 都会重建），用事件委托 */
document.addEventListener("input", function(e){
  if(e.target && e.target.id === "tellText"){
    S.tellText = e.target.value;
  }
});
function toggleBias(n){
  var i = bias.indexOf(n);
  if(i>=0){ bias.splice(i,1); toast("已移出本命"); } else { bias.push(n); toast("已加入本命"); }
  LS.set("bias", bias); render();
}
function addBias(n){ if(n && bias.indexOf(n)<0){ bias.push(n); LS.set("bias", bias); toast("已加入本命"); render(); } }

/* 搜索 */
var qt;
$("q").addEventListener("input", function(){
  var v = this.value; clearTimeout(qt);
  qt = setTimeout(function(){
    S.q = v.trim();
    /* 在首页输入搜索 → 自动切到日历界面看结果 */
    if(S.q && S.view === "home"){ S.view = "calendar"; if(S.tab!=="past") S.tab="past"; syncTabs(); }
    /* 搜索时要放开时间范围：否则范围还锁在「未来 30 天」，
       明明库里有这张历史专辑却搜不到（和直链进 past 时同样处理） */
    if(S.q && S.range.kind === "f30" && S.range.mode === "quick"){
      S.range = rangePreset("pall");
    }
    render();
  }, 170);
});
$("qclr").addEventListener("click", function(){ $("q").value = ""; S.q = ""; render(); });

/* 筛选控件 */
$("fType").addEventListener("change", function(){ S.type = this.value; render(); });
$("fKind").addEventListener("change", function(){ S.kind = this.value; render(); });
$("fAgency").addEventListener("change", function(){ S.agency = this.value; render(); });
$("fSort").addEventListener("change", function(){ S.sort = this.value; render(); });
$("cFav").addEventListener("click", function(){ S.onlyFav = !S.onlyFav; render(); });
$("cBias").addEventListener("click", function(){ S.onlyBias = !S.onlyBias; render(); });
$("cReset").addEventListener("click", function(){
  S.q=""; S.type=""; S.kind=""; S.agency=""; S.onlyFav=false; S.onlyBias=false;
  S.range = rangePreset("pall");
  CAL.view = "day"; calInit();
  $("q").value=""; $("fType").value=""; $("fKind").value=""; $("fAgency").value="";
  render(); renderCal();
});
$("searchToggle").addEventListener("click", function(){
  var c = $("searchCover");
  c.style.display = c.style.display === "none" ? "" : "none";
  if(c.style.display !== "none") $("q").focus();
});
/* 注意：qclr 只能有一个处理器。以前这里还有第二个，它看到输入已被第一个清空，
   就顺手把搜索框收起来了 —— 搜索框改成默认展开后，这个副作用会让人以为搜索坏了。 */
/* 本命管理入口挪进了「我的」页的切换条上方按钮 */
$("biasAdd").addEventListener("click", function(){ addBias($("biasInput").value.trim()); $("biasInput").value=""; });
$("biasInput").addEventListener("keydown", function(e){
  if(e.key === "Enter"){ addBias(this.value.trim()); this.value = ""; }
});
$("dateBtn").addEventListener("click", function(e){
  e.stopPropagation();
  if($("calPop").classList.contains("on")) closeCal(); else openCal();
});
$("calPrev").addEventListener("click", function(){
  if(CAL.view === "month"){ CAL.y--; }
  else { CAL.m--; if(CAL.m < 0){ CAL.m = 11; CAL.y--; } }
  renderCal();
});
$("calNext").addEventListener("click", function(){
  if(CAL.view === "month"){ CAL.y++; }
  else { CAL.m++; if(CAL.m > 11){ CAL.m = 0; CAL.y++; } }
  renderCal();
});
$("calClear").addEventListener("click", function(){
  S.range = rangePreset(S.tab === "past" ? "pall" : "f30");
  CAL.view = "day"; calInit(); renderCal(); render();
});
$("calApply").addEventListener("click", function(){
  if(!CAL.from){ toast("先在日历里点一个日期"); return; }
  var from = CAL.from, to = CAL.to || CAL.from;
  S.range = {mode:"custom", kind:"custom", from:from, to:to,
             label:(from === to) ? from : (from + " ~ " + to)};
  /* 日历只在「全部发布」里，自定义区间一律留在本页（该页本来就前后都能看） */
  if(S.tab !== "past"){ S.tab = "past"; syncTabs(); }
  closeCal(); render();
});
/* 注意：绝不能在 #calPop 上 stopPropagation，否则弹层内部的
   data-day / data-cal* 点击全部到不了下面的 document 委托。 */

/* 公司下拉 */
(function(){
  var set = {};
  ALL.forEach(function(r){ if(r._agency) set[r._agency] = 1; });
  $("fAgency").innerHTML = '<option value="">全部</option>'
    + Object.keys(set).sort().map(function(k){
        return '<option value="'+esc(k)+'">'+esc(k)+'</option>';
      }).join("");
})();

/* 公安备案号：拿到后只填数字（如 34010002000123），页脚自动出现并带上查询链接。
   写法参考：皖公网安备 34010002000123号 */
var GAJ_CODE = "34011102004379";   /* 公安备案号：皖公网安备 34011102004379号（2026-10-30 通过） */
(function(){
  var el = $("gaj"); if(!el || !GAJ_CODE) return;
  el.innerHTML = '<a href="http://www.beian.gov.cn/portal/registerSystemInfo?recordcode='
    + encodeURIComponent(GAJ_CODE) + '" target="_blank" rel="noopener">'
    + '皖公网安备 ' + GAJ_CODE + '号</a>';
})();

/* 数据新鲜度 */
(function(){
  var g = DATA.generated;
  if(!g){ $("noticeTxt").textContent = "数据未生成，请先运行更新脚本。"; $("notice").classList.add("on"); return; }
  var d = new Date(g.replace(" ", "T"));
  var h = (Date.now() - d.getTime()) / 3600000;
  var ge = $("genAt");
  if(ge){ ge.textContent = "数据更新于 " + g + " · "; }
  if(h > 30){
    $("noticeTxt").textContent = "数据更新于 " + g + "（已过 " + Math.floor(h) + " 小时）。"
      + "每天应自动更新一次，若未更新请检查计划任务。";
    $("notice").classList.add("on");
  }
})();
$("noticeBtn").addEventListener("click", function(){
  alert("更新方式：\n\n1）自动：双击 install_task.bat 注册后，每天固定时间自动运行。\n"
      + "2）手动：双击 update.bat。\n\n更新完成后刷新本页即可。");
});

S.range = rangePreset("f30");

/* 支持 URL 参数：#release=<id> 直达详情；#tab=<名>&from=<日期>&to=<日期> 预设筛选
   抽成函数：初始化时读一次，浏览器前进/后退（popstate）时再读一次。 */
function applyHash(){
  var h = location.hash || "";
  function arg(k){
    var m = new RegExp("[#&]" + k + "=([^&]+)").exec(h);
    return m ? decodeURIComponent(m[1]) : null;
  }
  var tab = arg("tab");
  if(["future","past","guide","mine","more"].indexOf(tab) >= 0){
    S.tab = tab; S.view = "calendar";
    /* 直链进过去时和点击标签一样纠正范围，否则默认「未来 30 天」会显示未来的专辑 */
    if(tab === "past" && S.range.kind === "f30" && S.range.mode === "quick"){
      S.range = rangePreset("p365");
    }
  } else if(["upcoming","month"].indexOf(tab) >= 0){
    S.tab = "future"; S.frange = tab === "month" ? "month" : "f7"; S.view = "calendar";
  } else if(tab === "history"){ S.tab = "past"; S.view = "calendar"; }
  else if(tab === "fav"){ S.tab = "mine"; S.mine = "fav"; S.view = "calendar"; }
  else if(tab === "bias"){ S.tab = "mine"; S.mine = "bias"; S.view = "calendar"; }
  if(arg("view") === "calendar") S.view = "calendar";
  if(arg("view") === "home"){ S.view = "home"; S.detailId = null; }
  var from = arg("from"), to = arg("to");
  if(from){
    S.range = {mode:"custom", kind:"custom", from:from,
               to:to || from, label:from + (to && to !== from ? " ~ " + to : "")};
  }
  var rid = arg("release");
  if(rid){ S.detailId = rid; S.view = "calendar"; }
  syncTabs();
}


initSelects();
/* 搜索框默认展开：以前要点放大镜才出来，新访客根本不知道有搜索。
   窄屏位置不够，仍然收起，点图标再展开。 */
$("searchCover").style.display = (window.innerWidth >= 700) ? "" : "none";
applyHash();
render();

/* 浏览器前进 / 后退：按地址还原页面（打开详情写了 #release，退回去就是列表） */
addEventListener("popstate", function(){ applyHash(); render(); });
})();
