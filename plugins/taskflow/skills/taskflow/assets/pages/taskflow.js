/* taskflow pages — shared behavior: theme toggle, feedback save, toast.
   The no-flash theme is applied by a tiny inline <script> in each page's <head>;
   this file only wires the toggle button and the save/flash helpers. */

function tfTheme(next){
  var html=document.documentElement;
  var cur=html.getAttribute('data-theme')||'dark';
  var t=next||(cur==='dark'?'light':'dark');
  html.setAttribute('data-theme',t);
  try{localStorage.setItem('taskflow-theme',t);}catch(e){}
  tfThemeLabel();
}
function tfThemeLabel(){
  var t=document.documentElement.getAttribute('data-theme')||'dark';
  var b=document.getElementById('themebtn');
  if(b)b.textContent=t==='dark'?'☀ Light':'☾ Dark';
}
document.addEventListener('DOMContentLoaded',tfThemeLabel);

function flash(msg,err){
  var t=document.getElementById('toast');if(!t)return;
  t.textContent=msg;t.className='toast show'+(err?' err':'');
  setTimeout(function(){t.className='toast'+(err?' err':'');},2800);
}

async function tfSave(file,data){
  var body=JSON.stringify({file:file,data:data});
  if(location.protocol.indexOf('http')===0){
    try{
      var r=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:body});
      var j=await r.json();
      if(j&&j.ok){flash('Saved next to the page: '+file);return;}
      throw new Error((j&&j.error)||'save failed');
    }catch(e){flash('Helper unavailable — downloading the file instead',true);}
  }
  var blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=file;
  document.body.appendChild(a);a.click();a.remove();
  flash('Downloaded: '+file);
}

/* ---- shared annotation engine -----------------------------------------------------------
   Draws the floating notes panel (drag + collapse + save) and owns the notes list.
   The two page kinds differ only in HOW a note is captured and HOW its marker is drawn —
   the caller supplies those via opts (isVisible / onArm / onRemove / drawMarkers). Returns a
   small API {add, remove, refresh, focusNote, isArmed}. Notes with a `range`/`badgeEl` field
   keep it live in memory but it is stripped on save. */
function tfAnnotate(opts){
  var isVisible=opts.isVisible||function(){return true;};
  var onArm=opts.onArm||function(){};
  var onRemove=opts.onRemove||function(){};
  var drawMarkers=opts.drawMarkers||function(){};
  var notes=[], seq=0, mode=false;

  var panel=document.createElement('div');
  panel.className='apanel';
  panel.innerHTML=
    '<div class="apanel-h"><span class="grip">⠿</span>'
    +'<span class="ptitle">NOTES <b class="cnt">0</b></span>'
    +'<button class="iconbtn tf-collapse" title="Collapse">▾</button></div>'
    +'<div class="apanel-b"><button class="tbtn tf-mode">Add a note</button>'
    +'<div class="modehint tf-modehint">'+(opts.idleHint||'mode: normal viewing')+'</div>'
    +'<div class="list tf-list"></div>'
    +'<div class="general"><label>NOTE ON THE WHOLE PAGE</label>'
    +'<textarea class="tf-general" placeholder="a note about the page as a whole (optional)"></textarea></div>'
    +'<div class="saverow"><button class="btn tf-save">Save the notes</button></div>'
    +'<div class="hint tf-hint">→ '+opts.file+' (next to this page)</div></div>';
  var shield=document.createElement('div');shield.className='dragshield';
  document.documentElement.appendChild(panel);
  document.documentElement.appendChild(shield);

  var q=function(s){return panel.querySelector(s);};
  var listEl=q('.tf-list'), cntEl=q('.cnt'), modeBtn=q('.tf-mode'),
      hintMode=q('.tf-modehint'), genEl=q('.tf-general');
  var onRestore=opts.onRestore||function(){return true;};

  function renderList(){
    var vis=notes.filter(isVisible);
    listEl.innerHTML='';
    if(!vis.length){var e=document.createElement('div');e.className='empty';
      e.textContent=opts.emptyText||'No notes yet.';listEl.appendChild(e);cntEl.textContent='0';return;}
    vis.forEach(function(n,i){
      var row=document.createElement('div');row.className='noterow';row.setAttribute('data-nid',n.id);
      var num=document.createElement('div');num.className='num';num.textContent=i+1;
      var ta=document.createElement('textarea');ta.placeholder='what to change here…';ta.value=n.comment;
      ta.addEventListener('input',function(e){n.comment=e.target.value;});
      var del=document.createElement('button');del.className='del';del.textContent='✕';del.title='delete';
      del.addEventListener('click',function(){remove(n.id);});
      row.appendChild(num);
      if(n.quote){var box=document.createElement('div');box.className='qt';
        var qt=document.createElement('div');qt.className='quote';qt.textContent='«'+n.quote+'»';qt.title=n.quote;
        box.appendChild(qt);
        // A restored note whose fragment is gone (the page text changed) keeps its comment and says so,
        // rather than disappearing or pointing at the wrong place.
        if(n.orphan){var w=document.createElement('div');w.className='orphan';
          w.textContent='fragment not found on the page';box.appendChild(w);}
        box.appendChild(ta);row.appendChild(box);}
      else{row.appendChild(ta);}
      row.appendChild(del);listEl.appendChild(row);
    });
    cntEl.textContent=vis.length;
  }
  function refresh(){renderList();drawMarkers(notes.filter(isVisible));}
  function add(extra){var n=Object.assign({id:++seq,comment:''},extra);notes.push(n);refresh();return n;}
  function remove(id){var i=-1;notes.forEach(function(x,k){if(x.id===id)i=k;});
    if(i>=0){var n=notes[i];notes.splice(i,1);onRemove(n);}refresh();}
  function focusNote(id){var r=listEl.querySelector('[data-nid="'+id+'"] textarea');if(r)r.focus();}

  modeBtn.addEventListener('click',function(){
    mode=!mode;modeBtn.classList.toggle('on',mode);
    modeBtn.textContent=mode?'Done':'Add a note';
    hintMode.textContent=mode?(opts.armHint||'mode: notes on'):(opts.idleHint||'mode: normal viewing');
    document.documentElement.classList.toggle('tf-arming',mode);
    onArm(mode);
  });
  q('.tf-collapse').addEventListener('click',function(){
    var c=panel.classList.toggle('collapsed');
    this.textContent=c?'▸':'▾';this.title=c?'Expand':'Collapse';
  });
  q('.tf-save').addEventListener('click',function(){
    var out=notes.map(function(n){var o={};for(var k in n){if(k!=='range'&&k!=='badgeEl')o[k]=n[k];}
      if(o.comment!=null)o.comment=(''+o.comment).trim();return o;});
    tfSave(opts.file,{task:opts.task,kind:opts.kind,ts:new Date().toISOString(),general:genEl.value.trim(),notes:out});
  });
  (function(){var h=q('.apanel-h'),dx=0,dy=0,drag=false;
    h.addEventListener('mousedown',function(e){if(e.target.closest('.iconbtn'))return;
      var r=panel.getBoundingClientRect();dx=e.clientX-r.left;dy=e.clientY-r.top;
      panel.style.right='auto';panel.style.left=r.left+'px';panel.style.top=r.top+'px';
      drag=true;shield.classList.add('on');e.preventDefault();});
    window.addEventListener('mousemove',function(e){if(!drag)return;
      var x=Math.max(4,Math.min(window.innerWidth-44,e.clientX-dx));
      var y=Math.max(4,Math.min(window.innerHeight-44,e.clientY-dy));
      panel.style.left=x+'px';panel.style.top=y+'px';});
    window.addEventListener('mouseup',function(){drag=false;shield.classList.remove('on');});
  })();

  // What was saved comes back on the next visit: the panel starts by reading its own file. Only saved
  // notes are restored — nothing is kept behind the user's back between visits.
  function restore(){
    if(location.protocol.indexOf('http')!==0)return;              // file:// has no helper to read from
    fetch(opts.file,{cache:'no-store'}).then(function(r){
      if(r.status===404)return null;                              // nothing saved yet — a normal first visit
      if(!r.ok)throw new Error('HTTP '+r.status);
      return r.json();
    }).then(function(data){
      if(!data)return;
      if(!data.notes||!data.notes.length){if(data.general)genEl.value=data.general;return;}
      if(data.general)genEl.value=data.general;
      data.notes.forEach(function(saved){
        var n=Object.assign({comment:''},saved);
        n.id=++seq;
        if(onRestore(n)===false)n.orphan=true;
        notes.push(n);
      });
      refresh();
      var lost=notes.filter(function(n){return n.orphan;}).length;
      flash(lost?('Notes restored: '+notes.length+', without a matching fragment: '+lost)
                :('Notes restored: '+notes.length));
    }).catch(function(e){
      // Saved feedback that cannot be read is reported, never silently treated as "no feedback".
      flash('Could not read '+opts.file+': '+e.message,true);
    });
  }

  renderList();
  restore();
  return {add:add,remove:remove,refresh:refresh,focusNote:focusNote,isArmed:function(){return mode;}};
}

/* ---- Find a saved quote again in the live page and hand back a Range over it.
   The quote was stored with whitespace collapsed, so the page text is walked the same way and each
   character of the collapsed string keeps a pointer back to its text node and offset. Text inside the
   panel and inside already-placed badges is skipped, or a restored badge would corrupt the next
   search. Returns null when the fragment is gone — the caller marks the note instead of guessing. ---- */
function tfFindQuote(root,quote){
  var want=String(quote||'').replace(/\s+/g,' ').trim();
  if(!want)return null;
  var walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:function(node){
    if(!node.nodeValue)return NodeFilter.FILTER_REJECT;
    var el=node.parentNode;
    if(el&&el.closest&&(el.closest('.apanel')||el.closest('.tf-badge')))return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }});
  var norm='',map=[],prevSpace=true,node;
  while((node=walker.nextNode())){
    var s=node.nodeValue;
    for(var i=0;i<s.length;i++){
      var isSpace=/\s/.test(s[i]);
      if(isSpace){if(prevSpace)continue;norm+=' ';}
      else norm+=s[i];
      map.push({node:node,off:i});
      prevSpace=isSpace;
    }
  }
  var at=norm.indexOf(want);
  if(at<0)return null;
  var a=map[at],b=map[at+want.length-1];
  if(!a||!b)return null;
  var range=document.createRange();
  range.setStart(a.node,a.off);
  range.setEnd(b.node,b.off+1);
  return range;
}

/* ---- Task / Plan pages: capture a text selection, pin a numbered badge after it, tint the fragment ---- */
function tfAnnotateDoc(opts){
  var root=document.querySelector('.wrap')||document.body;
  var anno=tfAnnotate({
    file:opts.file,task:opts.task,kind:opts.kind,
    idleHint:'select text on the page to leave a note',
    armHint:'mode: select a text fragment',
    emptyText:'Turn the mode on and select the text your note is about.',
    onRemove:function(n){if(n.badgeEl)n.badgeEl.remove();},
    onRestore:function(n){
      var range=tfFindQuote(root,n.quote);
      if(!range)return false;                       // the text moved or changed — say so, do not guess
      var badge=document.createElement('sup');badge.className='tf-badge';
      var end=range.cloneRange();end.collapse(false);
      try{end.insertNode(badge);}catch(e){return false;}
      n.range=range;n.badgeEl=badge;
      badge.addEventListener('click',function(){anno.focusNote(n.id);});
      return true;
    },
    drawMarkers:function(vis){
      vis.forEach(function(n,i){if(n.badgeEl)n.badgeEl.textContent=i+1;});
      if(window.CSS&&CSS.highlights&&window.Highlight){
        var rs=[];vis.forEach(function(n){if(n.range)rs.push(n.range);});
        if(rs.length)CSS.highlights.set('tf-note',new Highlight(...rs));
        else CSS.highlights.delete('tf-note');
      }
    }
  });
  function nearestLabel(node){
    var el=node.nodeType===1?node:node.parentNode;
    var block=el&&el.closest?el.closest('.block'):null;
    if(block){var lb=block.querySelector('.label');if(lb)return lb.textContent.trim();}
    return (document.title||'page').replace(/^#\S+\s·\s/,'');
  }
  document.addEventListener('mouseup',function(){
    if(!anno.isArmed())return;
    var sel=window.getSelection();
    if(!sel||sel.isCollapsed||!sel.rangeCount)return;
    var range=sel.getRangeAt(0);if(range.collapsed)return;
    var anc=range.commonAncestorContainer;var ancEl=anc.nodeType===1?anc:anc.parentNode;
    if(!ancEl||!root.contains(ancEl))return;              // ignore selections outside the content (e.g. the panel)
    var quote=sel.toString().replace(/\s+/g,' ').trim();if(!quote)return;
    var hl=range.cloneRange();
    var badge=document.createElement('sup');badge.className='tf-badge';
    var endR=range.cloneRange();endR.collapse(false);
    try{endR.insertNode(badge);}catch(e){return;}
    var note=anno.add({quote:quote,section:nearestLabel(range.startContainer),range:hl,badgeEl:badge});
    badge.addEventListener('click',function(){anno.focusNote(note.id);});
    sel.removeAllRanges();
  });
  return anno;
}

/* ---- Mockup: pins over the embedded mockup, scoped to whichever screen is currently shown ----
   The mockup announces its active screen via postMessage({tfScenario}); pins carry that screen
   id and only render while it is visible, so switching screens hides the others' pins. */
function tfAnnotateMockup(opts){
  var frame=document.getElementById(opts.frame||'mock');
  var stage=document.getElementById(opts.stage||'stage');
  var overlay=document.getElementById(opts.overlay||'overlay');
  var pinlayer=document.getElementById(opts.pinlayer||'pinlayer');
  var cur=null, curLabel='';
  function sendTheme(){var t=document.documentElement.getAttribute('data-theme')||'dark';
    try{frame.contentWindow.postMessage({tfTheme:t==='light'?'light':'dark'},'*');}catch(e){}}
  if(frame){frame.addEventListener('load',sendTheme);
    new MutationObserver(sendTheme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});}
  var anno=tfAnnotate({
    file:opts.file,task:opts.task,kind:opts.kind,
    idleHint:'mode: interact with the mockup',
    armHint:'mode: click the mockup to drop pins',
    emptyText:'Turn on "Add a note" and click the mockup.',
    isVisible:function(n){return !n.scenario||n.scenario===cur;},
    onArm:function(on){if(overlay)overlay.classList.toggle('arming',on);if(stage)stage.classList.toggle('arming',on);},
    drawMarkers:function(vis){if(!pinlayer)return;pinlayer.innerHTML='';
      vis.forEach(function(n,i){var d=document.createElement('div');d.className='pin';d.textContent=i+1;
        d.style.left=n.xPct+'%';d.style.top=n.yPct+'%';pinlayer.appendChild(d);});}
  });
  if(overlay)overlay.addEventListener('click',function(ev){
    if(!anno.isArmed())return;
    var r=stage.getBoundingClientRect();
    var x=(ev.clientX-r.left)/r.width*100, y=(ev.clientY-r.top)/r.height*100;
    if(x<0||x>100||y<0||y>100)return;
    anno.add({xPct:+x.toFixed(2),yPct:+y.toFixed(2),scenario:cur,scenarioLabel:curLabel});
  });
  window.addEventListener('message',function(e){
    if(e.data&&e.data.tfScenario){cur=e.data.tfScenario;curLabel=e.data.tfScenarioLabel||'';anno.refresh();}
  });
  return anno;
}
