#!/usr/bin/env python3
"""DOKARI Weather Radar: forecast + recent footage discovery; never verifies footage."""
import concurrent.futures
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'docs' / 'data.json'
NOW = dt.datetime.now(dt.timezone.utc)
UTC = dt.timezone.utc
USER_AGENT = 'Mozilla/5.0 (compatible; DokariWeatherRadar/4.0; editorial discovery)'
# Each run searches 5 YouTube queries (500 quota units); rotate over 3 daily runs.
SEARCHES = [
 ('USA','en','severe weather forecast USA storm warning'),
 ('USA','en','tornado outbreak forecast weather today'),
 ('USA','en','winter storm forecast snowfall alert'),
 ('Canada','en','Canada winter storm forecast warning'),
 ('UK','en','UK Met Office weather warning forecast'),
 ('Europe','en','Europe severe weather forecast ECMWF'),
 ('Greece','el','Ελλάδα πρόγνωση καιρού κακοκαιρία προειδοποίηση'),
 ('Turkey','tr','Türkiye meteoroloji hava durumu fırtına uyarısı'),
 ('Japan','ja','気象庁 大雪 台風 天気予報 警報'),
 ('Korea','ko','기상청 폭설 태풍 날씨 예보 특보'),
 ('Italy','it','previsioni meteo allerta maltempo temporali'),
 ('Germany','de','Wettervorhersage Unwetterwarnung Sturm'),
 ('Nordics','sv','väderprognos snöstorm varning'),
 ('India','hi','मौसम पूर्वानुमान भारी बारिश चेतावनी'),
 ('Global','en','tropical cyclone hurricane forecast latest'),
 ('USA','en','tornado storm damage eyewitness footage today'),
 ('Japan','ja','大雪 吹雪 現地映像 今日'),
 ('Turkey','tr','sel fırtına görüntüleri bugün'),
 ('Italy','it','alluvione maltempo immagini oggi'),
 ('Greece','el','κακοκαιρία πλημμύρα βίντεο σήμερα'),
 ('Canada','en','blizzard footage Canada today'),
 ('UK','en','flooding storm footage UK today'),
 ('Asia','en','typhoon flooding footage today'),
 ('Europe','en','hailstorm flash flood footage today'),
]
FORECAST = re.compile(r'forecast|prediction|outlook|warning|alert|watch|advisory|expected|could hit|risk|model|ecmwf|gfs|weather update|weather report|met office|meteorolog|πρόγνωσ|προειδοποίησ|επιδείνωσ|αναμένετ|καιρός|hava durumu|uyarısı|tahmin|天気予報|警報|予報|예보|특보|previsioni|allerta|vorhersage|warnung|väderprognos|varning|पूर्वानुमान|चेतावनी', re.I)
EVENT = re.compile(r'blizzard|snowstorm|heavy snow|whiteout|flood|flash flood|tornado|hurricane|typhoon|cyclone|hailstorm|severe thunderstorm|storm surge|wildfire|heatwave|χιονοθύελλ|χιονόπτωσ|πλημμύρ|κακοκαιρ|καταιγίδ|ανεμοστρόβιλ|τυφών|sel|fırtına|kar yağışı|吹雪|大雪|台風|洪水|폭설|태풍|홍수|alluvion|temporali|schneesturm|hochwasser|snöstorm|översvämning|बाढ़|तूफान', re.I)
FOOTAGE = re.compile(r'footage|caught on camera|on the ground|eyewitness|live from|现场|現地映像|映像|영상|görüntüleri|immagini|aufnahmen|βίντεο|εικόνες|today|σήμερα|bugün|oggi|heute', re.I)
BAD = re.compile(r'animation|animated|cartoon|anime|minecraft|roblox|fortnite|gameplay|gaming|walkthrough|trailer|movie|film scene|fiction|storytime|dog ran|dog relay|diphtheria|ai generated|ai-generated|made with ai|simulation|simulator|history of|historical|documentary|compilation|top 10|throwback|reaction video|school lesson|quiz|exam|시험|게임|アニメ|ゲーム|动画|游戏', re.I)
OLD = re.compile(r'\b(?:19[0-9]{2}|20(?:0[0-9]|1[0-9]|2[0-4]))\b', re.I)

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent':USER_AGENT,'Accept':'application/json,application/rss+xml,*/*'})
    with urllib.request.urlopen(req, timeout=16) as response:
        return response.read()

def clean(value):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',value or ''))).strip()

def parse_date(value):
    if not value: return None
    try:
        x=email.utils.parsedate_to_datetime(value)
    except (ValueError,TypeError,OverflowError):
        try: x=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        except (ValueError,TypeError,AttributeError): return None
    return x.replace(tzinfo=UTC) if x.tzinfo is None else x.astimezone(UTC)

def uid(platform,url):
    return hashlib.sha256((platform+'|'+url).encode()).hexdigest()[:20]

def assess(item):
    title=item.get('title','')
    published=parse_date(item.get('published_at'))
    age=(NOW-published).total_seconds()/3600 if published else 9999
    is_forecast=bool(FORECAST.search(title))
    is_event=bool(EVENT.search(title))
    is_footage=bool(FOOTAGE.search(title))
    rejected=bool(BAD.search(title) or OLD.search(title))
    # Forecasts are useful even when they discuss future events; no 'past footage' assumption.
    kind='FORECAST' if is_forecast else 'FOOTAGE' if is_event and is_footage else 'REVIEW'
    score=(45 if is_forecast else 40 if kind=='FOOTAGE' else 5)
    score+=20 if is_event else 0
    score+=15 if age<=24 else 8 if age<=48 else 0
    score+=8 if item.get('platform')=='YouTube' else 0
    if rejected or age>96: score=0
    item['content_type']=kind
    item['editorial_score']=min(score,100)
    item['editorial_priority']='REVIEW' if score<45 else 'HOT' if score>=75 else 'NEW'
    item['review_reason']='Possible irrelevant or archival content' if rejected else 'Check forecast validity or footage recording date, location, source and rights'
    item['verified']=False
    return item

def youtube_search(region,lang,query,api):
    params=urllib.parse.urlencode({'part':'snippet','q':query,'type':'video','order':'date','maxResults':12,'publishedAfter':(NOW-dt.timedelta(days=3)).isoformat().replace('+00:00','Z'),'key':api})
    data=json.loads(get('https://www.googleapis.com/youtube/v3/search?'+params))
    out=[]
    for x in data.get('items',[]):
        vid=x.get('id',{}).get('videoId')
        sn=x.get('snippet',{})
        if not vid: continue
        url='https://www.youtube.com/watch?v='+vid
        item={'id':uid('YouTube',url),'platform':'YouTube','region':region,'language':lang,'query':query,'title':clean(sn.get('title')),'url':url,'published_at':sn.get('publishedAt'),'found_at':NOW.isoformat(),'source':sn.get('channelTitle',''),'thumbnail':sn.get('thumbnails',{}).get('high',sn.get('thumbnails',{}).get('medium',{})).get('url',''),'status':'new','rights':'unknown','verified':False,'recorded_at':None,'notes':'YouTube upload date is not recording date; verify source and rights.'}
        item=assess(item)
        if item['editorial_score']>=45: out.append(item)
    return out

def rss_search(query):
    params=urllib.parse.urlencode({'q':query+' when:2d','hl':'en-US','gl':'US','ceid':'US:en'})
    root=ET.fromstring(get('https://news.google.com/rss/search?'+params))
    out=[]
    for x in root.findall('.//channel/item')[:12]:
        title=clean(x.findtext('title'))
        url=x.findtext('link') or ''
        published=parse_date(x.findtext('pubDate'))
        if not url or not published or (NOW-published).total_seconds()>72*3600: continue
        item={'id':uid('News RSS',url),'platform':'News RSS','region':'Global','language':'en','query':query,'title':title,'url':url,'published_at':published.isoformat(),'found_at':NOW.isoformat(),'source':clean(x.findtext('source')),'status':'new','rights':'unknown','verified':False,'recorded_at':None,'notes':'Article for context, not confirmed video. Region is Global unless verified.'}
        item=assess(item)
        if item['editorial_score']>=45: out.append(item)
    return out

def main():
    old=[]
    if DATA.exists():
        try: old=json.loads(DATA.read_text(encoding='utf-8')).get('items',[])
        except (OSError,ValueError): pass
    # Reassess old items and remove irrelevant entries; retain only 72h for freshness.
    found={}
    for item in old:
        item=assess(item)
        stamp=parse_date(item.get('found_at')) or parse_date(item.get('published_at'))
        if item.get('id') and stamp and stamp>=NOW-dt.timedelta(hours=72) and item['editorial_score']>=45:
            found[item['id']]=item
    errors=[]
    new_count=0
    api=os.environ.get('YOUTUBE_API_KEY','').strip()
    # Only 3 RSS searches per run to reduce Google News 429 rate limits.
    rss_queries=['severe weather warning forecast','extreme weather flooding storm today','winter storm typhoon cyclone forecast']
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for query,result in zip(rss_queries,pool.map(safe_rss,rss_queries)):
            items,error=result
            if error: errors.append('RSS '+query+': '+error)
            for item in items:
                if item['id'] not in found: new_count+=1
                found[item['id']]=item
    if api:
        slot=0 if NOW.hour<9 else 1 if NOW.hour<15 else 2
        start=((NOW.toordinal()*15)+(slot*5))%len(SEARCHES)
        for i in range(5):
            region,lang,query=SEARCHES[(start+i)%len(SEARCHES)]
            try:
                items=youtube_search(region,lang,query,api)
                for item in items:
                    if item['id'] not in found: new_count+=1
                    found[item['id']]=item
            except Exception as exc:
                errors.append(f'YouTube {query}: {type(exc).__name__}: {str(exc)[:130]}')
    items=sorted(found.values(),key=lambda x:(x.get('editorial_score',0),x.get('published_at') or ''),reverse=True)[:250]
    DATA.parent.mkdir(parents=True,exist_ok=True)
    DATA.write_text(json.dumps({'updated_at':NOW.isoformat(),'count':len(items),'new_count':new_count,'youtube_enabled':bool(api),'errors':errors[:20],'items':items},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Items: {len(items)} | New: {new_count} | YouTube: {sum(x.get("platform")=="YouTube" for x in items)} | Errors: {len(errors)}')
    if errors: print('\n'.join(errors[:5]))

def safe_rss(query):
    try: return rss_search(query),None
    except Exception as exc: return [],f'{type(exc).__name__}: {str(exc)[:130]}'

if __name__=='__main__': main()

