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
      if(j&&j.ok){flash('Saved next to the page: '+file);return {saved:true,file:file};}
      throw new Error((j&&j.error)||'save failed');
    }catch(e){flash('Helper unavailable — downloading the file instead',true);}
  }
  var blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=file;
  document.body.appendChild(a);a.click();a.remove();
  flash('Downloaded: '+file);
  return {saved:false,file:file};
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

  // The block is the same either way; only its housing differs. `opts.mount` (an element or its id)
  // puts it inside a host column that already exists on the page — the mockup's review column; with
  // no mount it becomes the floating, draggable panel the document pages use.
  var mount=typeof opts.mount==='string'?document.getElementById(opts.mount):(opts.mount||null);
  var inner=
    '<button class="tbtn tf-mode">Add a note</button>'
    +'<div class="modehint tf-modehint">'+(opts.idleHint||'mode: normal viewing')+'</div>'
    +'<div class="list tf-list"></div>'
    +'<div class="general"><label>NOTE ON THE WHOLE PAGE</label>'
    +'<textarea class="tf-general" placeholder="a note about the page as a whole (optional)"></textarea></div>'
    +'<div class="saverow"><button class="btn tf-save">Save the notes</button></div>'
    +'<div class="hint tf-hint">→ '+opts.file+' (next to this page)</div>';
  var panel=document.createElement('div');
  if(mount){
    panel.className='tfa';
    panel.innerHTML='<div class="mk-label">Notes <b class="cnt">0</b></div>'+inner;
    mount.hidden=false;
    mount.appendChild(panel);
  }else{
    panel.className='apanel';
    panel.innerHTML=
      '<div class="apanel-h"><span class="grip">⠿</span>'
      +'<span class="ptitle">NOTES <b class="cnt">0</b></span>'
      +'<button class="iconbtn tf-collapse" title="Collapse">▾</button></div>'
      +'<div class="apanel-b">'+inner+'</div>';
    var shield=document.createElement('div');shield.className='dragshield';
    document.documentElement.appendChild(panel);
    document.documentElement.appendChild(shield);
  }

  var q=function(s){return panel.querySelector(s);};
  var listEl=q('.tf-list'), cntEl=q('.cnt'), modeBtn=q('.tf-mode'),
      hintMode=q('.tf-modehint'), genEl=q('.tf-general'), hintEl=q('.tf-hint');
  // The toast is gone in three seconds, so the line under the button carries the state that lasts:
  // where the notes went, at what time, and whether anything has changed since.
  var savedOnce=false;
  function markDirty(){if(savedOnce)hintEl.textContent='● unsaved changes → '+opts.file;}
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
      ta.addEventListener('input',function(e){n.comment=e.target.value;markDirty();});
      var del=document.createElement('button');del.className='del';del.textContent='✕';del.title='delete';
      del.addEventListener('click',function(){remove(n.id);});
      row.appendChild(num);
      if(n.quote){var box=document.createElement('div');box.className='qt';
        var qt=document.createElement('div');qt.className='quote';qt.textContent='«'+n.quote+'»';qt.title=n.quote;
        box.appendChild(qt);
        // A restored note whose fragment is gone (the page text changed) keeps its comment and says so,
        // rather than disappearing or pointing at the wrong place.
        if(n.orphan){var w=document.createElement('div');w.className='orphan';
          w.textContent=opts.orphanText||'fragment not found on the page';box.appendChild(w);}
        box.appendChild(ta);row.appendChild(box);}
      else{row.appendChild(ta);}
      row.appendChild(del);listEl.appendChild(row);
    });
    cntEl.textContent=vis.length;
  }
  function refresh(){renderList();drawMarkers(notes.filter(isVisible));}
  function redrawMarkers(){drawMarkers(notes.filter(isVisible));}
  function add(extra){var n=Object.assign({id:++seq,comment:''},extra);notes.push(n);refresh();markDirty();return n;}
  function remove(id){var i=-1;notes.forEach(function(x,k){if(x.id===id)i=k;});
    if(i>=0){var n=notes[i];notes.splice(i,1);onRemove(n);}refresh();markDirty();}
  function focusNote(id){var r=listEl.querySelector('[data-nid="'+id+'"] textarea');if(r)r.focus();}

  function setMode(on){
    if(mode===on)return;
    mode=on;modeBtn.classList.toggle('on',mode);
    modeBtn.textContent=mode?'Done':'Add a note';
    hintMode.textContent=mode?(opts.armHint||'mode: notes on'):(opts.idleHint||'mode: normal viewing');
    document.documentElement.classList.toggle('tf-arming',mode);
    onArm(mode);
  }
  modeBtn.addEventListener('click',function(){setMode(!mode);});
  genEl.addEventListener('input',markDirty);
  if(q('.tf-collapse'))q('.tf-collapse').addEventListener('click',function(){
    var c=panel.classList.toggle('collapsed');
    this.textContent=c?'▸':'▾';this.title=c?'Expand':'Collapse';
  });
  q('.tf-save').addEventListener('click',function(){
    var out=notes.map(function(n){var o={};for(var k in n){if(k!=='range'&&k!=='badgeEl')o[k]=n[k];}
      if(o.comment!=null)o.comment=(''+o.comment).trim();return o;});
    setMode(false);                                   // saving ends the round of annotating
    tfSave(opts.file,{task:opts.task,kind:opts.kind,ts:new Date().toISOString(),general:genEl.value.trim(),notes:out})
      .then(function(r){
        var t=new Date(),hh=('0'+t.getHours()).slice(-2)+':'+('0'+t.getMinutes()).slice(-2);
        savedOnce=true;
        hintEl.textContent=(r&&r.saved?'✓ saved at '+hh+' → '+opts.file+' (next to this page)'
                                      :'↓ downloaded '+opts.file+' at '+hh);
      });
  });
  (function(){var h=q('.apanel-h'),dx=0,dy=0,drag=false;
    if(!h)return;                                     // mounted in a host column: nothing to drag
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
  return {add:add,remove:remove,refresh:refresh,redrawMarkers:redrawMarkers,
          focusNote:focusNote,isArmed:function(){return mode;}};
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

/* ---- Mockup: what the cursor is pointing at ------------------------------------------------
   A person points at one thing — a menu item, a button, a table cell — not at the decorative
   span inside it, so from the deepest node under the cursor we take the nearest ancestor that
   reads as a single control. A candidate covering most of the stage is refused: there the
   cursor is over empty space, and the note keeps its coordinates alone. Mark a region with
   `data-mk-el="Name"` to name it yourself and to make it a target on its own. ---- */
// Two tiers, nearest match wins within a tier. A control is asked about first, so an icon inside
// a button highlights the button; only where no control encloses the cursor does a content unit
// (cell, row, heading, paragraph, picture) answer; failing both, the node under the cursor itself.
var TF_EL_UNITS=[
  '[data-mk-el]','a','button','summary','label','input','select','textarea',
  '[role="button"]','[role="tab"]','[role="menuitem"]','[role="listitem"]','li'
].join(',');
var TF_EL_UNITS2=['td','th','tr','[role="row"]','h1','h2','h3','h4','h5','h6','p','img','svg','.card'].join(',');
var TF_EL_MAX_AREA=0.7;
var TF_EL_CHROME='.mk-overlay,.mk-pinlayer,.mk-hilite,.tfa,.apanel,.toast';

function tfElAt(stage,x,y){
  if(!stage||!document.elementsFromPoint)return null;
  var stack=document.elementsFromPoint(x,y),el=null;
  for(var i=0;i<stack.length;i++){
    var n=stack[i];
    if(n.closest&&n.closest(TF_EL_CHROME))continue;      // the review machinery is not part of the mockup
    if(n===stage||!stage.contains(n))continue;
    el=n;break;
  }
  if(!el)return null;
  var unit=el.closest(TF_EL_UNITS)||el.closest(TF_EL_UNITS2);
  if(unit&&unit!==stage&&stage.contains(unit))el=unit;
  var r=el.getBoundingClientRect(),s=stage.getBoundingClientRect();
  if(!r.width||!r.height)return null;
  if(s.width&&s.height&&(r.width*r.height)/(s.width*s.height)>TF_EL_MAX_AREA)return null;
  return el;
}

/* What the note calls the element: the author's own name first, then anything the product
   already shows to a reader, then the tag as a last resort. */
function tfElLabel(el){
  var v=el.getAttribute('data-mk-el')||el.getAttribute('aria-label')||el.getAttribute('alt')
       ||el.getAttribute('title')||((el.innerText||el.textContent||'')).replace(/\s+/g,' ').trim()
       ||el.getAttribute('placeholder')||el.value||'';
  v=(''+v).trim();
  if(v.length>80)v=v.slice(0,79)+'…';
  if(v)return v;
  var cls=typeof el.className==='string'?el.className.trim().split(/\s+/)[0]:'';
  return el.tagName.toLowerCase()+(cls?'.'+cls:'');
}

/* A path that finds the same element again on the next visit. Stops at the first id unique in
   the document; otherwise a child-position chain up to the stage. */
function tfElPath(stage,el){
  var parts=[],n=el;
  while(n&&n!==stage&&n.nodeType===1){
    if(n.id&&window.CSS&&CSS.escape&&document.querySelectorAll('#'+CSS.escape(n.id)).length===1){
      parts.unshift('#'+CSS.escape(n.id));break;
    }
    var i=1,sib=n;
    while((sib=sib.previousElementSibling))i++;
    parts.unshift(n.tagName.toLowerCase()+':nth-child('+i+')');
    n=n.parentNode;
  }
  return parts.join('>');
}

function tfElFind(stage,path){
  if(!stage||!path)return null;
  try{return stage.querySelector(path);}catch(e){return null;}
}

var TF_HILITE_CSS=
  // The engine owns how its own layers look and stack: the catching layer sits above the mockup's
  // sticky content (a pinned panel is otherwise unreachable) and below the review column.
   '.mk-stage .mk-overlay{z-index:40;}'
 +'.mk-stage .mk-overlay.arming{background:transparent;}'
 +'.mk-stage .mk-pinlayer{z-index:41;}'
 +'.mk-hilite{position:absolute;z-index:42;pointer-events:none;display:none;border-radius:5px;'
 +'border:1.5px solid color-mix(in srgb, var(--primary,#6366f1) 55%, transparent);}'
 +'.mk-hilite.on{display:block;}'
 +'.mk-hilite .lbl{position:absolute;left:-1px;top:-20px;max-width:340px;overflow:hidden;'
 +'white-space:nowrap;text-overflow:ellipsis;padding:0 5px;border-radius:3px;'
 +'background:var(--background,#fff);color:var(--primary,#6366f1);'
 +'border:1px solid color-mix(in srgb, var(--primary,#6366f1) 40%, transparent);'
 +'font:600 11px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;}'
 +'.mk-hilite[data-tf-edge="top"] .lbl{top:auto;bottom:-20px;}';

/* ---- Mockup: pins over the mockup, scoped to whichever screen is currently shown ----
   The mockup announces its active screen: as a `mk:scenario` event when it is this same document
   (the ui-mockup page carries its review column and the notes block inside it), or over
   postMessage({tfScenario}) when an older page embeds it in an iframe. Pins carry that screen id
   and only render while it is visible, so switching screens hides the others' pins. */
function tfAnnotateMockup(opts){
  var frame=opts.frame===null?null:document.getElementById(opts.frame||'mock');
  var stage=document.getElementById(opts.stage||'stage');
  var overlay=document.getElementById(opts.overlay||'overlay');
  var pinlayer=document.getElementById(opts.pinlayer||'pinlayer');
  var root=document.documentElement;
  var cur=root.getAttribute('data-mk-scenario'), curLabel=root.getAttribute('data-mk-scenario-label')||'';
  function sendTheme(){var t=document.documentElement.getAttribute('data-theme')||'dark';
    try{frame.contentWindow.postMessage({tfTheme:t==='light'?'light':'dark'},'*');}catch(e){}}
  if(frame){frame.addEventListener('load',sendTheme);
    new MutationObserver(sendTheme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});}
  // The box drawn around whatever the cursor is over while the mode is on. Element and styles are
  // created here, so a mockup page written before this needs no markup of its own.
  var hil=null;
  // The sheet goes in as the block is wired, not on first hover: it is what lifts the catching layer
  // over the mockup's own content, and without it the first hover there never arrives.
  if(stage&&!document.getElementById('tf-hilite-css')){
    var tfst=document.createElement('style');tfst.id='tf-hilite-css';tfst.textContent=TF_HILITE_CSS;
    document.head.appendChild(tfst);
  }
  function hilite(){
    if(hil||!stage)return hil;
    hil=document.createElement('div');hil.className='mk-hilite';
    hil.innerHTML='<span class="lbl"></span>';
    stage.appendChild(hil);
    return hil;
  }
  function showHilite(el){
    var h=hilite();if(!h)return;
    var r=el.getBoundingClientRect(),s=stage.getBoundingClientRect();
    h.style.left=(r.left-s.left)+'px';h.style.top=(r.top-s.top)+'px';
    h.style.width=r.width+'px';h.style.height=r.height+'px';
    h.setAttribute('data-tf-edge',r.top-s.top<22?'top':'');
    h.querySelector('.lbl').textContent=tfElLabel(el);
    h.classList.add('on');
  }
  function hideHilite(){if(hil)hil.classList.remove('on');}

  var anno=tfAnnotate({
    file:opts.file,task:opts.task,kind:opts.kind,mount:opts.mount,
    idleHint:'mode: interact with the mockup',
    armHint:'mode: hover an element and click',
    emptyText:'Turn on "Add a note" and click the mockup.',
    orphanText:'element not found on the mockup — the note holds its place',
    isVisible:function(n){return !n.scenario||n.scenario===cur;},
    onArm:function(on){if(overlay)overlay.classList.toggle('arming',on);if(stage)stage.classList.toggle('arming',on);
      if(!on)hideHilite();},
    onRestore:function(n){return !(n.el&&n.el.path)||!!tfElFind(stage,n.el.path);},
    drawMarkers:function(vis){if(!pinlayer||!stage)return;pinlayer.innerHTML='';
      var s=stage.getBoundingClientRect();
      vis.forEach(function(n,i){
        var d=document.createElement('div');d.className='pin';d.textContent=i+1;
        var x=n.xPct,y=n.yPct;
        // The click point is where the user actually pointed, so it wins while it still falls on the
        // element. Once the layout has moved it elsewhere, the pin follows the element instead.
        var el=n.el&&n.el.path?tfElFind(stage,n.el.path):null;
        if(el&&s.width&&s.height){
          var r=el.getBoundingClientRect();
          var px=s.left+x/100*s.width, py=s.top+y/100*s.height;
          var inside=px>=r.left&&px<=r.right&&py>=r.top&&py<=r.bottom;
          if(r.width&&r.height&&!inside){
            x=(r.left-s.left+Math.min(18,r.width/2))/s.width*100;
            y=(r.top-s.top+Math.min(18,r.height/2))/s.height*100;
          }
        }
        d.style.left=x+'%';d.style.top=y+'%';
        if(n.quote)d.title=n.quote;
        pinlayer.appendChild(d);});}
  });

  // Hovering is only possible where the mockup shares this document; an embedded frame keeps
  // coordinates alone.
  if(overlay&&!frame){
    overlay.addEventListener('mousemove',function(ev){
      if(!anno.isArmed())return;
      var el=tfElAt(stage,ev.clientX,ev.clientY);
      if(el)showHilite(el);else hideHilite();
    });
    overlay.addEventListener('mouseleave',hideHilite);
  }
  if(overlay)overlay.addEventListener('click',function(ev){
    if(!anno.isArmed())return;
    var r=stage.getBoundingClientRect();
    var x=(ev.clientX-r.left)/r.width*100, y=(ev.clientY-r.top)/r.height*100;
    if(x<0||x>100||y<0||y>100)return;
    var n={xPct:+x.toFixed(2),yPct:+y.toFixed(2),scenario:cur,scenarioLabel:curLabel};
    var el=frame?null:tfElAt(stage,ev.clientX,ev.clientY);
    if(el){n.quote=tfElLabel(el);n.el={path:tfElPath(stage,el),tag:el.tagName.toLowerCase()};}
    anno.add(n);
  });
  // Scrolling inside the mockup moves the elements under the pins: element-bound ones are redrawn
  // where their element now is. The list is left alone — re-rendering it would drop the cursor out
  // of a comment being typed.
  if(stage)stage.addEventListener('scroll',function(){
    hideHilite();
    if(window.requestAnimationFrame)requestAnimationFrame(anno.redrawMarkers);
    else anno.redrawMarkers();
  },true);
  document.addEventListener('mk:scenario',function(e){
    cur=e.detail&&e.detail.id;curLabel=(e.detail&&e.detail.label)||'';anno.refresh();
  });
  window.addEventListener('message',function(e){
    if(e.data&&e.data.tfScenario){cur=e.data.tfScenario;curLabel=e.data.tfScenarioLabel||'';anno.refresh();}
  });
  return anno;
}
