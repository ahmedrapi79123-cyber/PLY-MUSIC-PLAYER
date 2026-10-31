(() => {
  const $ = (id) => document.getElementById(id);
  const audio = $('audio-player'), video = $('video-player');
  const tracks = [];
  let current = -1, view = 'all', shuffle = false, repeat = false, newestFirst = true, toastTimer;
  const audioExt = /\.(mp3|m4a|aac|ogg|oga|wav|flac|opus|weba)(?:$|[?#])/i;
  const videoExt = /\.(mp4|webm|ogv|mov|m4v)(?:$|[?#])/i;
  const formatTime = (n) => Number.isFinite(n) ? `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, '0')}` : '—:——';
  const esc = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function toast(message) { const el=$('toast'); el.textContent=message; el.classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.classList.remove('show'),3000); }
  function kindFor(file, url='') { const type=(file?.type||'').toLowerCase(), name=(file?.name||url).toLowerCase(); return type.startsWith('video/')||videoExt.test(name)?'video':'audio'; }
  function addTrack(file, url, title) {
    const kind=kindFor(file,url); const name=title || (file?.name || decodeURIComponent(url.split('/').pop().split(/[?#]/)[0]) || 'وسيط بدون اسم');
    if (tracks.some(t=>t.name===name && t.url===url)) return;
    tracks.push({file,url,name,kind,duration:NaN});
  }
  function playlistText(text, base='') {
    let title=''; let added=0;
    for (const raw of text.replace(/^\uFEFF/,'').split(/\r?\n/)) {
      const line=raw.trim(); if(!line) continue;
      if(line.startsWith('#EXTINF:')) { title=line.slice(line.indexOf(',')+1).trim(); continue; }
      if(line.startsWith('#')) continue;
      let url=line;
      try { url=new URL(line,base || location.href).href; } catch {}
      if (/^https?:|^blob:|^file:/i.test(url)) { addTrack(null,url,title || undefined); added++; }
      else toast('القائمة فيها مسارات محلية؛ اختار ملفات الصوت والفيديو من جهازك كمان.');
      title='';
    }
    return added;
  }
  function importFiles(files) {
    let playlists=0, media=0;
    for(const file of files) {
      if (/\.m3u8?$/i.test(file.name) || /mpegurl/i.test(file.type)) { playlists+=playlistTextSafe(file); }
      else { addTrack(file,URL.createObjectURL(file)); media++; }
    }
    render();
    if(media||playlists) toast(`${media ? `${media} ملف` : ''}${media&&playlists?'، ':''}${playlists ? `${playlists} عنصر من قائمة التشغيل` : ''} اتضاف${(media+playlists)>2?'وا':'وا'}`);
  }
  function playlistTextSafe(file) {
    const reader=new FileReader();
    reader.onload=()=>{const count=playlistText(String(reader.result||'')); render(); toast(count?`تم استيراد ${count} عنصر من القائمة`:'ملف القائمة لا يحتوي على روابط قابلة للتشغيل');};
    reader.onerror=()=>toast('تعذرت قراءة ملف قائمة التشغيل'); reader.readAsText(file); return 0;
  }
  function visibleTracks() {
    const q=$('search').value.trim().toLocaleLowerCase();
    let list=tracks.filter(t=>(view==='all'||t.kind===view)&&(!q||t.name.toLocaleLowerCase().includes(q)));
    return newestFirst?list.slice().reverse():list;
  }
  function render() {
    $('all-count').textContent=tracks.length; $('audio-count').textContent=tracks.filter(t=>t.kind==='audio').length; $('video-count').textContent=tracks.filter(t=>t.kind==='video').length;
    $('item-summary').textContent=tracks.length?`${tracks.length} ${tracks.length===1?'ملف':'ملفات'} في مكتبتك`:'ملفاتك ستظهر هنا';
    const list=visibleTracks(), container=$('track-list');
    if(!list.length){container.innerHTML=`<div class="empty-state"><div class="empty-icon">♫</div><strong>${tracks.length?'مفيش نتائج للبحث':'مكتبتك لسه فاضية'}</strong><p>${tracks.length?'جرّب اسمًا مختلفًا.':'اسحب ملفات MP3 أو MP4 إلى هنا، أو اخترها من جهازك.'}</p>${tracks.length?'':`<button class="outline-button" id="empty-import">اختار ملفات</button>`}</div>`; const b=$('empty-import');if(b)b.onclick=()=> $('file-input').click();}
    else container.innerHTML=list.map(t=>{const idx=tracks.indexOf(t);return `<div class="track-row"><div class="track-info" data-play="${idx}"><div class="mini-cover ${t.kind}">${t.kind==='video'?'▹':'♫'}</div><div class="track-text"><strong>${esc(t.name)}</strong><small>${t.file?esc(t.file.type|| (t.kind==='video'?'MP4':'MP3')):'قائمة تشغيل'}</small></div></div><span class="track-kind">${t.kind==='video'?'فيديو':'صوت'}</span><span class="track-duration">${formatTime(t.duration)}</span><button class="row-play" data-play="${idx}" title="تشغيل">▶</button></div>`}).join('');
    container.querySelectorAll('[data-play]').forEach(el=>el.addEventListener('click',()=>play(Number(el.dataset.play))));
    const queue=$('queue-list'); const rest=tracks.map((t,i)=>({t,i})).filter(x=>x.i!==current).slice(0,8);
    queue.innerHTML=rest.length?rest.map(({t,i})=>`<div class="queue-item" data-play="${i}"><div class="mini-cover ${t.kind}">${t.kind==='video'?'▹':'♫'}</div><div><strong>${esc(t.name)}</strong><small>${t.kind==='video'?'فيديو':'صوت'} · ${formatTime(t.duration)}</small></div></div>`).join(''):'<div class="queue-empty">أضف ملفات لتظهر هنا</div>';
    queue.querySelectorAll('[data-play]').forEach(el=>el.addEventListener('click',()=>play(Number(el.dataset.play))));
  }
  function activePlayer(){return current>=0&&tracks[current]?.kind==='video'?video:audio;}
  function play(index) {
    if(!tracks.length)return;
    current=(index+tracks.length)%tracks.length; const t=tracks[current]; const p=t.kind==='video'?video:audio, other=t.kind==='video'?audio:video;
    other.pause(); other.removeAttribute('src'); other.load(); p.src=t.url; p.volume=Number($('volume').value); $('now-title').textContent=t.name; $('now-subtitle').textContent=t.kind==='video'?'فيديو':'ملف صوتي'; $('play').textContent='Ⅱ';
    video.style.display=t.kind==='video'?'block':'none'; $('cover-wrap').style.display=t.kind==='video'?'none':'';
    p.play().then(()=>{}).catch(()=>{ $('play').textContent='▶'; toast('المتصفح مش قادر يشغّل الملف أو الرابط ده.'); }); render();
  }
  function togglePlay(){if(current<0){if(tracks.length)play(0);else $('file-input').click();return;}const p=activePlayer();if(p.paused)p.play().then(()=>$('play').textContent='Ⅱ').catch(()=>{});else{p.pause();$('play').textContent='▶';}}
  function next(){if(!tracks.length)return;play(shuffle?Math.floor(Math.random()*tracks.length):(current+1)%tracks.length);}
  function previous(){if(!tracks.length)return;const p=activePlayer();if(p.currentTime>3){p.currentTime=0;return;}play((current-1+tracks.length)%tracks.length);}
  for(const p of [audio,video]){
    p.addEventListener('loadedmetadata',()=>{if(current>=0){tracks[current].duration=p.duration; $('total-time').textContent=formatTime(p.duration); render();}});
    p.addEventListener('timeupdate',()=>{if(p!==activePlayer())return;$('current-time').textContent=formatTime(p.currentTime);$('seek').value=p.duration?p.currentTime/p.duration*100:0;});
    p.addEventListener('ended',()=>{if(repeat){p.currentTime=0;p.play();}else if(current<tracks.length-1||shuffle)next();else{$('play').textContent='▶';$('seek').value=0;}});
    p.addEventListener('play',()=>{$('play').textContent='Ⅱ';});p.addEventListener('pause',()=>{$('play').textContent='▶';});
  }
  $('open-files').onclick=$('hero-import').onclick=$('empty-import').onclick=()=> $('file-input').click();
  $('file-input').addEventListener('change',e=>{importFiles(e.target.files);e.target.value='';});
  $('add-playlist').onclick=()=> $('playlist-input').click();
  $('playlist-input').addEventListener('change',e=>{if(e.target.files[0])playlistTextSafe(e.target.files[0]);e.target.value='';});
  document.querySelectorAll('.nav-item').forEach(btn=>btn.onclick=()=>{view=btn.dataset.view;document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b===btn));$('view-title').textContent={all:'كل الوسائط',audio:'الصوتيات',video:'الفيديوهات'}[view];$('section-title').textContent={all:'أضيفت مؤخرًا',audio:'الصوتيات',video:'الفيديوهات'}[view];render();});
  $('search').addEventListener('input',render);
  $('sort-button').onclick=()=>{newestFirst=!newestFirst;$('sort-button').innerHTML=(newestFirst?'الأحدث أولًا':'الأقدم أولًا')+' <span>⌄</span>';render();};
  $('play').onclick=togglePlay;$('next').onclick=next;$('previous').onclick=previous;
  $('shuffle').onclick=()=>{$('shuffle').classList.toggle('active',shuffle=!shuffle);toast(shuffle?'التشغيل العشوائي مفعّل':'التشغيل العشوائي متوقف');};
  $('repeat').onclick=()=>{$('repeat').classList.toggle('active',repeat=!repeat);toast(repeat?'تكرار المسار مفعّل':'تكرار المسار متوقف');};
  $('seek').oninput=e=>{const p=activePlayer();if(Number.isFinite(p.duration))p.currentTime=p.duration*Number(e.target.value)/100;};
  $('volume').oninput=e=>{audio.volume=video.volume=Number(e.target.value);};
  $('clear-queue').onclick=()=>{tracks.forEach(t=>{if(t.url.startsWith('blob:'))URL.revokeObjectURL(t.url)});tracks.length=0;audio.pause();video.pause();audio.removeAttribute('src');video.removeAttribute('src');current=-1;$('now-title').textContent='لا يوجد شيء قيد التشغيل';$('now-subtitle').textContent='أضف ملفاتك للبدء';$('play').textContent='▶';$('cover-wrap').style.display='';video.style.display='none';render();};
  $('theme-toggle').onclick=()=>document.body.classList.toggle('light');
  document.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','BUTTON'].includes(document.activeElement.tagName)){e.preventDefault();togglePlay();}if(e.code==='ArrowRight'&&e.altKey)next();if(e.code==='ArrowLeft'&&e.altKey)previous();});
  window.addEventListener('dragover',e=>{e.preventDefault();document.body.classList.add('drop-active');});
  window.addEventListener('dragleave',e=>{if(!e.relatedTarget)document.body.classList.remove('drop-active');});
  window.addEventListener('drop',e=>{e.preventDefault();document.body.classList.remove('drop-active');if(e.dataTransfer.files.length)importFiles(e.dataTransfer.files);else{const text=e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('text/plain');if(text)playlistText(text);}});
  render();
})();
