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

/* 发行形态：只分 单曲 / 迷你专(EP) / 正规专 三类。
   后续专、合辑归入正规专，避免筛选时多余一档。 */
function catOf(r){
  var t = (r.rtype||"").toLowerCase();
  if(t.indexOf("mini")>=0 || /\bep\b/.test(t) || t.indexOf("- ep")>=0) return "Mini";
  if(t.indexOf("single")>=0) return "Single";
  return "Album";
}
function typeLabel(r){
  var c = r._cat;
  if(c==="Mini") return "迷你专 EP";
  if(c==="Single") return "单曲";
  return "正规专";
}

/* 规范化 */
ALL.forEach(function(r){
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
  r._tracks = r.tracks || [];
  r._tn = r._tracks.length || 0;
  r._dur = r.durationMs || 0;
  if(!r._dur && r._tracks.length){
    r._dur = r._tracks.reduce(function(s,t){ return s + (t.ms||0); }, 0);
  }
});
/* 搜索索引 */
ALL.forEach(function(r){
  var d = dispName(r.artist);
  r._hay = [r.artist, d.zh, r.title, r._agency, r._fandom,
            (ART[r.artist]&&ART[r.artist].name_ko)||"", r.rtype||"", r.genre||""]
           .join(" ").toLowerCase();
});
var DATE_COUNT = {};
ALL.forEach(function(r){ if(r.date) DATE_COUNT[r.date] = (DATE_COUNT[r.date]||0)+1; });

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
  tab:"upcoming", q:"", type:"", kind:"", agency:"", sort:"date_asc",
  onlyFav:false, onlyBias:false,
  range:{mode:"quick", from:null, to:null, label:"未来 30 天"},
  upRange:"f30",                       /* 即将回归：只能是 f7 / f30 */
  showBiasMgr:false, detailId:null,
  calMonth:null, calFrom:null, calTo:null
};

/* 时间范围预设 */
function rangePreset(kind){
  var t = new Date(TODAY), f, to, lb;
  if(kind==="f7"){ f=d2s(t); var e=new Date(t); e.setDate(e.getDate()+7); to=d2s(e); lb="未来 7 天"; }
  else if(kind==="f30"){ f=d2s(t); var e2=new Date(t); e2.setDate(e2.getDate()+30); to=d2s(e2); lb="未来 30 天"; }
  else if(kind==="f90"){ f=d2s(t); var e3=new Date(t); e3.setDate(e3.getDate()+90); to=d2s(e3); lb="未来 90 天"; }
  else if(kind==="all"){ f=null; to=null; lb="全部未来"; }
  else if(kind==="p30"){ var s1=new Date(t); s1.setDate(s1.getDate()-30); f=d2s(s1); to=d2s(t); lb="过去 30 天"; }
  else if(kind==="p365"){ var s2=new Date(t); s2.setDate(s2.getDate()-365); f=d2s(s2); to=d2s(t); lb="过去 1 年"; }
  else if(kind==="pall"){ f=null; to=null; lb="全部已发布"; }
  else if(kind==="month"){ var y=t.getFullYear(), m=t.getMonth(); f=d2s(new Date(y,m,1)); to=d2s(new Date(y,m+1,0)); lb=y+" 年 "+(m+1)+" 月"; }
  else if(kind==="ytd"){ var y2=t.getFullYear(); f=y2+"-01-01"; to=d2s(t); lb=y2+" 年至今"; }
  else if(kind==="lyr"){ var y3=t.getFullYear()-1; f=y3+"-01-01"; to=y3+"-12-31"; lb=y3+" 年"; }
  else { f=d2s(t); var e4=new Date(t); e4.setDate(e4.getDate()+30); to=d2s(e4); lb="未来 30 天"; }
  return {mode:"quick", kind:kind, from:f, to:to, label:lb};
}

/* ============================ 筛选 ============================ */
/* 各页签实际生效的时间范围：
   即将回归 → 只能 7 天 / 30 天；本月回归 → 固定当月；全部发布 → 用日历/预设。 */
function activeRange(){
  if(S.tab === "month")    return rangePreset("month");
  if(S.tab === "upcoming") return rangePreset(S.upRange || "f30");
  return S.range;
}
function inRange(r){
  var R = activeRange();
  if(R.kind==="all") return r._dd >= 0;
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
    +   '<div class="ph">🎵</div>'
    +   (r._img ? '<img loading="lazy" src="'+esc(r._img)+'" alt="" onerror="this.style.display=\'none\'">' : '')
    +   ddayHTML(r)
    +   '<button class="favbtn'+(fa?' on':'')+'" data-fav="'+esc(r.id)+'" title="收藏">'+(fa?'★':'☆')+'</button>'
    +   badges
    + '</div>'
    + '<div class="cbody">'
    +   '<div class="ctitle">'+esc(r.title)+'</div>'
    +   '<div class="car">'+heartHTML(r.artist)
    +     '<span class="zh">'+esc(dn.zh)+'</span>'
    +     (dn.en ? '<span class="en">'+esc(dn.en)+'</span>' : '')
    +   '</div>'
    +   '<div class="cmeta"><span class="tag">'+esc(typeLabel(r))+'</span>'
    +     (r._tn ? '<span class="tag s">'+r._tn+' 首</span>' : '')
    +     (r._agency ? '<span>'+esc(r._agency)+'</span>' : '')
    +     '<span>'+esc(r.date)+'</span></div>'
    + '</div></div>';
}
function gridHTML(list){
  if(!list.length) return '<div class="empty"><div class="e">🎧</div><h3>没有匹配的发行</h3>'
    + '<p>试试调整时间范围或筛选条件</p></div>';
  return '<div class="grid">' + list.map(cardHTML).join("") + '</div>';
}
function secHTML(title, list){
  if(!list.length) return "";
  return '<div class="sec-h"><h2>'+esc(title)+'</h2><span class="c">'+list.length+'</span>'
       + '<span class="line"></span></div>' + gridHTML(list);
}

/* ============================ 详情页 ============================ */
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
    +  '<div class="art"><div class="ph">🎵</div>'
    +    (r._img ? '<img src="'+esc(r._img)+'" alt="" onerror="this.style.display=\'none\'">' : '')
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
    +      (r.genre ? '<span class="sep">·</span><span>'+esc(r.genre)+'</span>' : '')
    +      '<span class="sep">·</span><span class="tag">'+esc(typeLabel(r))+'</span>'
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

  h += '<div class="dact">'
    +  '<button class="btn" id="favDetail" style="padding:10px 18px;border-radius:11px;font-size:13px">'
    +    (isFav(r.id) ? '★ 已收藏' : '☆ 收藏') + '</button>'
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
        +   '<div class="exi"><span class="k">风格</span><span class="v">'+esc(t.g || r.genre || "—")+'</span></div>'
        +   '<div class="exi"><span class="k">制作团队</span><span class="v dim">暂未收录</span></div>'
        +  '</div>'
        +  '<div class="extnote">说明：作词 / 作曲 / 编曲等制作人员名单，Apple Music 的公开接口并不提供，'
        +   '维基与 MusicBrainz 对 K-pop 新作的收录率也几乎为零，因此暂不展示。'
        +   '时长、曲序、风格为官方接口原始数据。</div>'
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
function renderStats(){
  var up = ALL.filter(function(r){ return r._dd>=0 && r._dd<=30; });
  var bi = up.filter(function(r){ return isBias(r.artist); });
  var nw = ALL.filter(function(r){ return r._isNew && r._dd>=0; });
  var past = ALL.filter(function(r){ return r._dd<0; });
  $("stats").innerHTML =
      '<div class="stat"><div class="k">未来 30 天回归</div><div class="v">'+up.length+'</div></div>'
    + '<div class="stat'+(bi.length?' hl':'')+'"><div class="k">本命即将回归</div><div class="v">'+bi.length+'</div></div>'
    + '<div class="stat"><div class="k">新人待发</div><div class="v">'+nw.length+'</div></div>'
    + '<div class="stat"><div class="k">已收录发行</div><div class="v">'+past.length+'</div></div>'
    + '<div class="stat"><div class="k">追踪艺人</div><div class="v">'+Object.keys(ART).length+'</div></div>';
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
function renderList(){
  $("biasN").textContent = bias.length;
  /* 角标跟页面实际展示的量对齐：切 7 天就显示 7 天的数 */
  var upN = (S.upRange||"f30")==="f7"
    ? ALL.filter(function(r){ return r._dd>=0 && r._dd<=7; }).length
    : ALL.filter(function(r){ return r._dd>=0 && r._dd<=30; }).length;
  $("nUp").textContent = upN;
  $("nMo").textContent = ALL.filter(inThisMonth).length;
  $("nHi").textContent = ALL.filter(function(r){ return r._dd<0; }).length;
  $("nFa").textContent = favs.length;
  $("nBi").textContent = ALL.filter(function(r){ return isBias(r.artist); }).length;

  renderStats();
  renderBiasBox();
  $("biasBox").style.display = (S.tab==="bias" || S.showBiasMgr) ? "" : "none";
  $("dateLabel").textContent = S.range.label;
  $("dateBtn").classList.toggle("on", S.range.mode === "custom");

  /* 控制条显隐：只有「全部发布」才有完整筛选 */
  var isUp = (S.tab==="upcoming"), isMo = (S.tab==="month"), isHi = (S.tab==="history");
  $("upBar").classList.toggle("on", isUp);
  $("moBar").classList.toggle("on", isMo);
  $("filters").style.display = isHi ? "" : "none";

  if(isUp){
    document.querySelectorAll("#upBar [data-up]").forEach(function(b){
      b.classList.toggle("on", b.getAttribute("data-up") === (S.upRange||"f30"));
    });
  }
  if(isMo){
    var R = monthRange();
    var mn = ALL.filter(inThisMonth);
    var nU = mn.filter(function(r){ return r._dd>=0; }).length;
    $("moLabel").textContent = R.label;
    $("moSub").textContent = "共 " + mn.length + " 张 · 其中 " + nU + " 张还没发行";
  }

  var html = "";
  if(isUp){
    // 时间已由 upBar 限定为 7 / 30 天，这里只按日期排，不再分组
    var ul = applyFilters(ALL).filter(function(r){ return r._dd >= 0; })
               .sort(function(a,b){ return a._dd - b._dd; });
    html = ul.length
      ? '<div class="sec-h"><h2>' + esc((S.upRange||"f30")==="f7" ? "未来 7 天" : "未来 30 天")
        + '</h2><span class="c">' + ul.length + '</span><span class="line"></span></div>'
        + gridHTML(ul)
      : '<div class="empty"><div class="e">🎧</div><h3>这段时间没有回归</h3>'
        + '<p>换「未来 30 天」看看，或去「全部发布」翻历史</p></div>';
  } else if(isMo){
    var ml = applyFilters(ALL).sort(function(a,b){ return (a.date||"").localeCompare(b.date||""); });
    html = ml.length ? gridHTML(ml)
      : '<div class="empty"><div class="e">🎧</div><h3>本月还没有回归记录</h3>'
        + '<p>数据每天自动更新</p></div>';
  } else if(S.tab==="history"){
    // 同理，切到全部发布后也可以看未来的
    html = gridHTML(applyFilters(ALL));
  } else if(S.tab==="fav"){
    var fl = ALL.filter(function(r){ return isFav(r.id); });
    var fu = fl.filter(function(r){ return r._dd>=0; }).sort(function(a,b){ return a._dd-b._dd; });
    var fp = fl.filter(function(r){ return r._dd<0; });
    html = fl.length ? secHTML("收藏 · 即将发行", fu) + secHTML("收藏 · 已发行", fp)
      : '<div class="empty"><div class="e">★</div><h3>还没有收藏</h3><p>在卡片右上角点 ☆ 即可收藏</p></div>';
  } else if(S.tab==="bias"){
    if(!bias.length){
      html = '<div class="empty"><div class="e">&#10084;</div><h3>还没有设置本命</h3>'
           + '<p>在上方「本命团体管理」里添加，或点卡片上的爱心</p></div>';
    } else {
      var bl = ALL.filter(function(r){ return isBias(r.artist); });
      var bu = bl.filter(function(r){ return r._dd>=0; }).sort(function(a,b){ return a._dd-b._dd; });
      var bp = bl.filter(function(r){ return r._dd<0; });
      html = secHTML("本命 · 即将发行", bu) + secHTML("本命 · 已发行", bp);
      if(!html) html = '<div class="empty"><div class="e">&#10084;</div><h3>本命暂无记录</h3><p>数据每天更新</p></div>';
    }
  }
  $("content").innerHTML = html;
  $("cFav").classList.toggle("on", S.onlyFav);
  $("cBias").classList.toggle("on", S.onlyBias);
  $("cReset").style.display = (S.q||S.type||S.kind||S.agency||S.onlyFav||S.onlyBias) ? "" : "none";
  $("qclr").classList.toggle("on", !!S.q);
}
function render(){
  if(S.detailId){
    $("listView").style.display = "none";
    $("detailView").style.display = "";
    var r = null;
    for(var i=0;i<ALL.length;i++){ if(ALL[i].id===S.detailId){ r=ALL[i]; break; } }
    if(!r){ S.detailId=null; render(); return; }
    $("detailView").innerHTML = detailHTML(r);
    window.scrollTo({top:0,behavior:"instant"});
  } else {
    $("listView").style.display = "";
    $("detailView").style.display = "none";
    renderList();
  }
}
function openDetail(id){ S.detailId = id; render(); }

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

  var qs = [
    ["f7","未来 7 天"],["f30","未来 30 天"],["f90","未来 90 天"],["all","全部未来"],
    ["p30","过去 30 天"],["month","本月"],["p365","过去 1 年"],["pall","全部已发布"],
    ["ytd","今年至今"],["lyr","去年"]
  ];
  $("calQuick").innerHTML = qs.map(function(q){
    var on = (S.range.kind === q[0]);
    return '<button class="chip'+(on?' on':'')+'" data-quick="'+q[0]+'">'+q[1]+'</button>';
  }).join("");

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
function setQuick(kind){
  /* 快捷预设只作用于「全部发布」——日历就在那一页的筛选栏里 */
  S.range = rangePreset(kind);
  if(S.tab !== "history"){ S.tab = "history"; syncTabs(); }
  CAL.y = TODAY.getFullYear(); CAL.m = TODAY.getMonth();
  CAL.from = S.range.from; CAL.to = S.range.to; CAL.picking = false;
  renderCal(); render();
}
function syncTabs(){
  document.querySelectorAll(".tab").forEach(function(x){
    x.classList.toggle("on", x.getAttribute("data-tab") === S.tab);
  });
}

/* ============================ 赞赏 ============================ */
/* 收款码：现在放的是占位图。把你的微信 / 支付宝收款码转成 base64 填进下面两行的
   引号里即可，填好后页面自动显示你自己的收款码（转 base64 这步可以让我帮你做）。 */
var PAY_QR = {
  wechat: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Crect width='200' height='200' fill='%23f6f7fb'/%3E%3Crect x='60' y='56' width='80' height='80' rx='10' fill='none' stroke='%23c9cddc' stroke-width='2' stroke-dasharray='6 4'/%3E%3Ctext x='100' y='98' text-anchor='middle' font-size='13' font-weight='bold' fill='%239aa0b4' font-family='sans-serif'%3E%E6%94%B6%E6%AC%BE%E7%A0%81%3C/text%3E%3Ctext x='100' y='120' text-anchor='middle' font-size='11' fill='%23b3b8c8' font-family='sans-serif'%3E%E5%BE%AE%E4%BF%A1%20%C2%B7%20%E5%BE%85%E4%B8%8A%E4%BC%A0%3C/text%3E%3C/svg%3E",
  alipay: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Crect width='200' height='200' fill='%23f6f7fb'/%3E%3Crect x='60' y='56' width='80' height='80' rx='10' fill='none' stroke='%23b9c6dd' stroke-width='2' stroke-dasharray='6 4'/%3E%3Ctext x='100' y='98' text-anchor='middle' font-size='13' font-weight='bold' fill='%239aa0b4' font-family='sans-serif'%3E%E6%94%B6%E6%AC%BE%E7%A0%81%3C/text%3E%3Ctext x='100' y='120' text-anchor='middle' font-size='11' fill='%23b3b8c8' font-family='sans-serif'%3E%E6%94%AF%E4%BB%98%E5%AE%9D%20%C2%B7%20%E5%BE%85%E4%B8%8A%E4%BC%A0%3C/text%3E%3C/svg%3E"
};
function SponShow(kind){
  var img = $("sponImg");
  if(img){ img.src = PAY_QR[kind] || PAY_QR.wechat; }
}
SponShow("wechat");

/* ============================ 事件 ============================ */
document.addEventListener("click", function(e){
  var t = e.target, el;

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

  /* 本命爱心 */
  if((el = t.closest("[data-heart]"))){
    e.stopPropagation();
    var art = el.getAttribute("data-heart");
    var i = bias.indexOf(art);
    if(i >= 0){ bias.splice(i,1); toast("已移出本命"); }
    else { bias.push(art); el.classList.add("pop"); burst(el); toast("已加入本命 ❤"); }
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
    if(j >= 0){ favs.splice(j,1); toast("已取消收藏"); } else { favs.push(id); toast("已收藏 ★"); }
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
  if((el = t.closest("[data-quick]"))){ setQuick(el.getAttribute("data-quick")); closeCal(); return; }
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
  if(t.id === "backBtn"){ S.detailId = null; render(); return; }
  if(t.id === "brandHome"){ S.detailId = null; render(); return; }
  /* 收藏按钮（详情页） */
  if(t.id === "favDetail"){
    var cur = S.detailId; var k = favs.indexOf(cur);
    if(k>=0){ favs.splice(k,1); toast("已取消收藏"); } else { favs.push(cur); toast("已收藏 ★"); }
    LS.set("favs", favs); render(); return;
  }
  /* 即将回归的 7 天 / 30 天切换 */
  if((el = t.closest("[data-up]"))){
    S.upRange = el.getAttribute("data-up"); render(); return;
  }
  /* Tab */
  if((el = t.closest(".tab"))){
    S.tab = el.getAttribute("data-tab"); S.detailId = null;
    /* 「即将回归」「本月回归」不带筛选，各自用固定范围，
       所以这里的 S.range 只服务于「全部发布」。 */
    if(S.tab==="history" && S.range.kind==="f30" && S.range.mode==="quick"){
      S.range = rangePreset("p365");
    }
    syncTabs(); render(); window.scrollTo({top:0,behavior:"smooth"}); return;
  }
  /* 点击空白关日历 */
  if(!t.closest("#calPop") && !t.closest("#dateBtn")) closeCal();
});
function toggleBias(n){
  var i = bias.indexOf(n);
  if(i>=0){ bias.splice(i,1); toast("已移出本命"); } else { bias.push(n); toast("已加入本命 ❤"); }
  LS.set("bias", bias); render();
}
function addBias(n){ if(n && bias.indexOf(n)<0){ bias.push(n); LS.set("bias", bias); toast("已加入本命 ❤"); render(); } }

/* 搜索 */
var qt;
$("q").addEventListener("input", function(){
  var v = this.value; clearTimeout(qt);
  qt = setTimeout(function(){ S.q = v.trim(); render(); }, 170);
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
$("btnBiasMgr").addEventListener("click", function(){
  S.showBiasMgr = !S.showBiasMgr;
  if(S.showBiasMgr){ S.tab = "bias"; syncTabs(); }
  render();
});
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
  S.range = rangePreset(S.tab === "history" ? "pall" : "f30");
  CAL.view = "day"; calInit(); renderCal(); render();
});
$("calApply").addEventListener("click", function(){
  if(!CAL.from){ toast("先在日历里点一个日期"); return; }
  var from = CAL.from, to = CAL.to || CAL.from;
  S.range = {mode:"custom", kind:"custom", from:from, to:to,
             label:(from === to) ? from : (from + " ~ " + to)};
  /* 日历只在「全部发布」里，自定义区间一律留在本页（该页本来就前后都能看） */
  if(S.tab !== "history"){ S.tab = "history"; syncTabs(); }
  closeCal(); render();
});
/* 注意：绝不能在 #calPop 上 stopPropagation，否则弹层内部的
   data-day / data-quick / data-cal* 点击全部到不了下面的 document 委托。 */

/* 公司下拉 */
(function(){
  var set = {};
  ALL.forEach(function(r){ if(r._agency) set[r._agency] = 1; });
  $("fAgency").innerHTML = '<option value="">全部</option>'
    + Object.keys(set).sort().map(function(k){
        return '<option value="'+esc(k)+'">'+esc(k)+'</option>';
      }).join("");
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

/* 支持 URL 参数：#release=<id> 直达详情；#tab=<名>&from=<日期>&to=<日期> 预设筛选 */
(function(){
  var h = location.hash || "";
  function arg(k){
    var m = new RegExp("[#&]" + k + "=([^&]+)").exec(h);
    return m ? decodeURIComponent(m[1]) : null;
  }
  var tab = arg("tab");
  if(tab && ["upcoming","month","history","fav","bias"].indexOf(tab) >= 0) S.tab = tab;
  var from = arg("from"), to = arg("to");
  if(from){
    S.range = {mode:"custom", kind:"custom", from:from,
               to:to || from, label:from + (to && to !== from ? " ~ " + to : "")};
  }
  var rid = arg("release");
  if(rid){ S.detailId = rid; }
  if(tab){ syncTabs(); }
})();

render();
})();
