(() => {
  const $ = (id) => document.getElementById(id);
  const audio = $('audio-player'), video = $('video-player');
  const tracks = [];
  const radioStation={file:null,url:'https://stream.radiojar.com/8s5u5tpdtwzuv',name:'إذاعة القرآن الكريم من القاهرة',artist:'بث مباشر',kind:'audio',duration:NaN,builtIn:true};
  function ensureRadioStation(){if(!tracks.some(track=>track.builtIn))tracks.unshift({...radioStation});}
  let current = -1, view = 'all', shuffle = false, repeat = false, newestFirst = true, toastTimer;
  let appleTimer,appleRequest,appleResults=[],appleQuery='',appleState='idle';
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
    list=newestFirst?list.slice().reverse():list;
    return list.sort((a,b)=>Number(Boolean(b.builtIn))-Number(Boolean(a.builtIn)));
  }
  const searchServices=[
    {name:'Spotify',url:q=>`https://open.spotify.com/search/${encodeURIComponent(q)}`,icon:'●'},
    {name:'YouTube Music',url:q=>`https://music.youtube.com/search?q=${encodeURIComponent(q)}`,icon:'▶'},
    {name:'SoundCloud',url:q=>`https://soundcloud.com/search?q=${encodeURIComponent(q)}`,icon:'☁'},
    {name:'Mixcloud',url:q=>`https://www.mixcloud.com/search/?q=${encodeURIComponent(q)}`,icon:'◉'},
    {name:'Bandcamp',url:q=>`https://bandcamp.com/search?q=${encodeURIComponent(q)}`,icon:'b'},
    {name:'Deezer',url:q=>`https://www.deezer.com/search/${encodeURIComponent(q)}`,icon:'≋'},
    {name:'TIDAL',url:q=>`https://listen.tidal.com/search?q=${encodeURIComponent(q)}`,icon:'◆'}
  ];
  function searchOnline(){
    const query=$('search').value.trim();clearTimeout(appleTimer);
    if(!query){appleResults=[];appleQuery='';appleState='idle';render();return;}
    if(query===appleQuery&&appleState==='loading')return;
    appleQuery=query;appleState='loading';render();
    appleTimer=setTimeout(async()=>{
      if(appleRequest)appleRequest.abort();appleRequest=new AbortController();
      try{
        const endpoint=`https://itunes.apple.com/search?${new URLSearchParams({term:query,entity:'song',limit:'15',country:'eg'})}`;
        const response=await fetch(endpoint,{signal:appleRequest.signal});
        if(!response.ok)throw new Error('search failed');
        const data=await response.json();if($('search').value.trim()!==query)return;
        appleResults=(data.results||[]).map(song=>({name:song.trackName,artist:song.artistName,album:song.collectionName,url:song.trackViewUrl,artwork:(song.artworkUrl100||'').replace('100x100','300x300'),duration:(song.trackTimeMillis||0)/1000,preview:song.previewUrl||''}));
        appleState='done';render();
      }catch(error){if(error.name==='AbortError')return;appleResults=[];appleState='error';render();}
    },400);
  }
  function playApplePreview(index){const result=appleResults[index];if(!result?.preview){toast('المعاينة غير متاحة للأغنية دي.');return;}let track=tracks.find(t=>t.url===result.preview);if(!track){track={file:null,url:result.preview,name:result.name,artist:result.artist,album:result.album,artwork:result.artwork,kind:'audio',duration:result.duration};tracks.push(track);}play(tracks.indexOf(track));}
  function embeddedSource(input){
    let url;try{url=new URL(input);}catch{return null;}
    if(url.protocol!=='https:')return null;
    const host=url.hostname.toLowerCase().replace(/^www\./,'');
    if(host==='open.spotify.com'||host==='spotify.com'){
      const match=url.pathname.match(/\/(?:intl-[a-z]{2}\/)?(track|album|playlist|artist|episode|show)\/([A-Za-z0-9]+)/);
      return match?{name:'Spotify',src:`https://open.spotify.com/embed/${match[1]}/${match[2]}?utm_source=generator&theme=0`,height:352}:null;
    }
    if(host==='youtube.com'||host==='m.youtube.com'||host==='music.youtube.com'||host==='youtu.be'){
      const id=host==='youtu.be'?url.pathname.slice(1):url.searchParams.get('v')||url.pathname.match(/\/(?:embed|shorts)\/([^/?]+)/)?.[1];
      const playlist=url.searchParams.get('list');
      if(playlist&&/^[A-Za-z0-9_-]+$/.test(playlist))return{name:'YouTube',src:`https://www.youtube.com/embed/videoseries?list=${playlist}`,height:390};
      if(id&&/^[A-Za-z0-9_-]{6,20}$/.test(id))return{name:'YouTube',src:`https://www.youtube.com/embed/${id}?playsinline=1`,height:390};
      return null;
    }
    if(host==='soundcloud.com'&&!url.pathname.startsWith('/search'))return{name:'SoundCloud',src:`https://w.soundcloud.com/player/?url=${encodeURIComponent(url.href)}&color=%23b99cff&auto_play=false&hide_related=true&show_comments=false&show_user=true&show_reposts=false&visual=true`,height:450};
    if(host==='mixcloud.com'&&!url.pathname.startsWith('/discover'))return{name:'Mixcloud',src:`https://www.mixcloud.com/widget/iframe/?hide_cover=1&feed=${encodeURIComponent(url.href)}`,height:300};
    if(host==='audiomack.com'){
      const match=url.pathname.match(/^\/(song|album)\/([^/]+)\/([^/]+)/);
      if(match)return{name:'Audiomack',src:`https://audiomack.com/embed/${match[1]}/${match[2]}/${match[3]}`,height:252};
    }
    if(host==='music.apple.com'&&/^\/(?:[a-z]{2}\/)?(?:album|playlist|song|music-video)\//.test(url.pathname))return{name:'Apple Music',src:url.href.replace('https://music.apple.com/','https://embed.music.apple.com/'),height:450};
    if(host==='deezer.com'){
      const match=url.pathname.match(/\/(?:[a-z]{2}\/)?(track|album|playlist|artist)\/(\d+)/);
      if(match)return{name:'Deezer',src:`https://widget.deezer.com/widget/dark/${match[1]}/${match[2]}?autoplay=false`,height:352};
    }
    if(host==='tidal.com'){
      const match=url.pathname.match(/\/(?:browse\/)?(track|album|playlist|video)\/(\d+)/);
      if(match)return{name:'TIDAL',src:`https://embed.tidal.com/${match[1]}s/${match[2]}`,height:352};
    }
    return null;
  }
  function render() {
    $('all-count').textContent=tracks.length; $('audio-count').textContent=tracks.filter(t=>t.kind==='audio').length; $('video-count').textContent=tracks.filter(t=>t.kind==='video').length;
    const query=$('search').value.trim();
    $('item-summary').textContent=query?`نتائج البحث عن «${query}»`:tracks.length?`${tracks.length} ${tracks.length===1?'ملف':'ملفات'} في مكتبتك`:'ملفاتك ستظهر هنا';
    $('radio-shortcut').classList.toggle('active',current>=0&&tracks[current]?.builtIn);
    $('search-clear').hidden=!query;
    $('section-title').textContent=query?'نتائج البحث':({all:'أضيفت مؤخرًا',audio:'الصوتيات',video:'الفيديوهات'}[view]);
    const list=visibleTracks(), container=$('track-list');
    if(query){
      const localMatches=tracks.map((track,index)=>({track,index})).filter(({track})=>track.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
      $('item-summary').textContent=`${localMatches.length} نتيجة في مكتبتك · بحث على منصات الموسيقى`;
      const localRows=localMatches.map(({track,index})=>`<div class="track-row"><div class="track-info" data-play="${index}"><div class="mini-cover ${track.kind}"${track.artwork?` style="background-image:url('${esc(track.artwork)}')`:''}>${track.artwork?'':track.kind==='video'?'▹':'♫'}</div><div class="track-text"><strong>${esc(track.name)}</strong><small>${esc(track.artist||(track.file?(track.file.type||(track.kind==='video'?'MP4':'MP3')):'قائمة تشغيل'))}</small></div></div><span class="track-kind">${track.kind==='video'?'فيديو':'صوت'}</span><span class="track-duration">${formatTime(track.duration)}</span><button class="row-play" data-play="${index}" title="تشغيل">▶</button></div>`).join('');
      const appleRows=appleResults.map((song,index)=>`<div class="track-row apple-result"><div class="track-info">${song.artwork?`<img class="mini-cover" src="${esc(song.artwork)}" alt="">`:'<div class="mini-cover">♫</div>'}<div class="track-text"><strong>${esc(song.name)}</strong><small>${esc(song.artist)} · ${esc(song.album||'')}</small></div></div><span class="track-kind">أغنية</span><span class="track-duration">${formatTime(song.duration)}</span>${song.preview?`<button class="row-play" data-apple-play="${index}" title="تشغيل المعاينة">▶</button>`:'<span class="no-preview">—</span>'}<a class="store-link" href="${esc(song.url)}" target="_blank" rel="noopener noreferrer">Apple Music</a></div>`).join('');
      const appleSection=appleState==='loading'?'<p class="search-note">بنبحث في iTunes…</p>':appleState==='error'?'<p class="search-note">تعذر الاتصال ببحث iTunes. جرّب تاني.</p>':appleState==='done'?(appleRows?`<div class="apple-results">${appleRows}<p class="apple-credit">معاينات الأغاني مقدمة من iTunes · <a href="https://www.apple.com/itunes/">افتح الأغنية على Apple Music</a></p></div>`:'<p class="search-note">مفيش نتائج على iTunes للبحث ده.</p>'):'';
      container.innerHTML=`<section class="local-search-results"><h3>في مكتبتك <span>${localMatches.length}</span></h3>${localRows||'<p class="search-note">مفيش ملفات مطابقة في مكتبتك.</p>'}</section><section class="apple-search-results"><h3>نتائج iTunes / Apple Music</h3>${appleSection}</section><section class="online-search-results"><h3>ابحث على الإنترنت</h3><div class="web-search-grid">${searchServices.map(service=>`<a class="web-search-card" href="${service.url(query)}" target="_blank" rel="noopener noreferrer"><span class="service-icon">${service.icon}</span><span><strong>${service.name}</strong><small>عرض نتائج البحث ↗</small></span><span class="service-arrow">↗</span></a>`).join('')}</div><p class="search-note">المنصات تفتح نتائجها في مشغّلاتها؛ Spotify وYouTube Music متاحان بدون ربط API.</p></section>`;
      container.querySelectorAll('[data-play]').forEach(el=>el.addEventListener('click',()=>play(Number(el.dataset.play))));
      container.querySelectorAll('[data-apple-play]').forEach(el=>el.addEventListener('click',()=>playApplePreview(Number(el.dataset.applePlay))));
      return;
    }
    if(!list.length){container.innerHTML=`<div class="empty-state"><div class="empty-icon">♫</div><strong>${tracks.length?'مفيش ملفات في القسم ده':'مكتبتك لسه فاضية'}</strong><p>${tracks.length?'غيّر القسم أو أضف وسائط للمكتبة.':'أضف ملفاتك عشان تلاقيها وتسمعها هنا.'}</p>${tracks.length?'':`<button class="outline-button" id="empty-import">اختار ملفات</button>`}</div>`; const b=$('empty-import');if(b)b.onclick=()=> $('file-input').click();}
    else container.innerHTML=list.map(t=>{const idx=tracks.indexOf(t);return `<div class="track-row"><div class="track-info" data-play="${idx}"><div class="mini-cover ${t.kind}"${t.artwork?` style="background-image:url('${esc(t.artwork)}')"`:''}>${t.artwork?'':t.kind==='video'?'▹':'♫'}</div><div class="track-text"><strong>${esc(t.name)}</strong><small>${esc(t.artist|| (t.file?(t.file.type|| (t.kind==='video'?'MP4':'MP3')):'قائمة تشغيل'))}</small></div></div><span class="track-kind">${t.kind==='video'?'فيديو':'صوت'}</span><span class="track-duration">${formatTime(t.duration)}</span><button class="row-play" data-play="${idx}" title="تشغيل">▶</button></div>`}).join('');
    container.querySelectorAll('[data-play]').forEach(el=>el.addEventListener('click',()=>play(Number(el.dataset.play))));
    const queue=$('queue-list'); const rest=tracks.map((t,i)=>({t,i})).filter(x=>x.i!==current).slice(0,8);
    queue.innerHTML=rest.length?rest.map(({t,i})=>`<div class="queue-item" data-play="${i}"><div class="mini-cover ${t.kind}">${t.kind==='video'?'▹':'♫'}</div><div><strong>${esc(t.name)}</strong><small>${t.kind==='video'?'فيديو':'صوت'} · ${formatTime(t.duration)}</small></div></div>`).join(''):'<div class="queue-empty">أضف ملفات لتظهر هنا</div>';
    queue.querySelectorAll('[data-play]').forEach(el=>el.addEventListener('click',()=>play(Number(el.dataset.play))));
  }
  function activePlayer(){return current>=0&&tracks[current]?.kind==='video'?video:audio;}
  function play(index) {
    if(!tracks.length)return;
    current=(index+tracks.length)%tracks.length; const t=tracks[current]; const p=t.kind==='video'?video:audio, other=t.kind==='video'?audio:video;
    other.pause(); other.removeAttribute('src'); other.load(); p.src=t.url; p.volume=Number($('volume').value); $('now-title').textContent=t.name; $('now-subtitle').textContent=t.artist|| (t.kind==='video'?'فيديو':'ملف صوتي'); $('play').textContent='Ⅱ';
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
  $('radio-shortcut').onclick=()=>{const index=tracks.findIndex(track=>track.builtIn);if(index>=0)play(index);};
  $('playlist-input').addEventListener('change',e=>{if(e.target.files[0])playlistTextSafe(e.target.files[0]);e.target.value='';});
  document.querySelectorAll('.nav-item').forEach(btn=>btn.onclick=()=>{view=btn.dataset.view;document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b===btn));$('view-title').textContent={all:'كل الوسائط',audio:'الصوتيات',video:'الفيديوهات'}[view];$('section-title').textContent={all:'أضيفت مؤخرًا',audio:'الصوتيات',video:'الفيديوهات'}[view];render();});
  $('search').addEventListener('input',searchOnline);
  $('search-clear').onclick=()=>{$('search').value='';$('search').focus();searchOnline();};
  $('share-link-form').addEventListener('submit',e=>{e.preventDefault();const link=$('share-link').value.trim(),embed=embeddedSource(link);if(!embed){toast('الرابط ده مش مدعوم. استخدم رابط مشاركة مباشر من منصة مدعومة.');return;}const list=$('track-list');list.innerHTML=`<div class="embedded-player"><div class="embedded-player-heading"><strong>تشغيل عبر ${esc(embed.name)}</strong><a href="${esc(link)}" target="_blank" rel="noopener noreferrer">فتح المصدر ↗</a></div><iframe src="${esc(embed.src)}" title="مشغل ${esc(embed.name)}" height="${embed.height}" allow="autoplay; encrypted-media; clipboard-write; fullscreen; picture-in-picture" allowfullscreen loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe></div>`;$('section-title').textContent='مشغل الإنترنت';$('item-summary').textContent='المشغل مضمّن داخل PLY';});
  $('sort-button').onclick=()=>{newestFirst=!newestFirst;$('sort-button').innerHTML=(newestFirst?'الأحدث أولًا':'الأقدم أولًا')+' <span>⌄</span>';render();};
  $('play').onclick=togglePlay;$('next').onclick=next;$('previous').onclick=previous;
  $('shuffle').onclick=()=>{$('shuffle').classList.toggle('active',shuffle=!shuffle);toast(shuffle?'التشغيل العشوائي مفعّل':'التشغيل العشوائي متوقف');};
  $('repeat').onclick=()=>{$('repeat').classList.toggle('active',repeat=!repeat);toast(repeat?'تكرار المسار مفعّل':'تكرار المسار متوقف');};
  $('seek').oninput=e=>{const p=activePlayer();if(Number.isFinite(p.duration))p.currentTime=p.duration*Number(e.target.value)/100;};
  $('volume').oninput=e=>{audio.volume=video.volume=Number(e.target.value);};
  $('clear-queue').onclick=()=>{tracks.forEach(t=>{if(t.url.startsWith('blob:'))URL.revokeObjectURL(t.url)});tracks.length=0;ensureRadioStation();audio.pause();video.pause();audio.removeAttribute('src');video.removeAttribute('src');current=-1;$('now-title').textContent='لا يوجد شيء قيد التشغيل';$('now-subtitle').textContent='أضف ملفاتك للبدء';$('play').textContent='▶';$('cover-wrap').style.display='';video.style.display='none';render();};
  $('theme-toggle').onclick=()=>document.body.classList.toggle('light');
  document.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','BUTTON'].includes(document.activeElement.tagName)){e.preventDefault();togglePlay();}if(e.code==='ArrowRight'&&e.altKey)next();if(e.code==='ArrowLeft'&&e.altKey)previous();});
  window.addEventListener('dragover',e=>{e.preventDefault();document.body.classList.add('drop-active');});
  window.addEventListener('dragleave',e=>{if(!e.relatedTarget)document.body.classList.remove('drop-active');});
  window.addEventListener('drop',e=>{e.preventDefault();document.body.classList.remove('drop-active');if(e.dataTransfer.files.length)importFiles(e.dataTransfer.files);else{const text=e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('text/plain');if(text)playlistText(text);}});
  ensureRadioStation();render();
})();
