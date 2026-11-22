#!/usr/bin/env python3
"""DOKARI Weather Radar: editorial discovery, never automatic verification."""
import concurrent.futures
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'docs' / 'data.json'
UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)
USER_AGENT = 'DokariWeatherRadar/3.0 (editorial discovery)'

# Searches rotate: five YouTube search.list requests per scheduled run.
QUERIES = [
 ('Turkey','tr','sel baskını şiddetli yağış görüntüleri'),
 ('Turkey','tr','kar fırtınası yoğun kar yağışı görüntüleri'),
 ('Turkey','tr','hortum dolu fırtına görüntüleri'),
 ('Japan','ja','大雪 吹雪 現地映像'),
 ('Japan','ja','豪雨 洪水 現地映像'),
 ('Japan','ja','台風 強風 被害 映像'),
 ('South Korea','ko','폭설 눈보라 현장 영상'),
 ('South Korea','ko','폭우 홍수 현장 영상'),
 ('China','zh','暴雪 现场 视频'),
 ('China','zh','暴雨 洪水 现场 视频'),
 ('Nordics','no','snøstorm ekstremvær video'),
 ('Nordics','sv','snöstorm oväder översvämning'),
 ('Nordics','fi','lumimyrsky tulva video'),
 ('Alps','it','forte nevicata valanga video'),
 ('Alps','de','Schneesturm Lawine Hochwasser aktuell'),
 ('USA','en','tornado damage eyewitness footage'),
 ('USA','en','flash flooding storm footage today'),
 ('USA','en','blizzard lake effect snow footage'),
 ('Canada','en','snowstorm blizzard flooding footage'),
 ('Canada','fr','tempête de neige inondation images'),
 ('Alaska','en','Alaska blizzard storm footage'),
 ('Greenland','en','Greenland blizzard storm footage'),
 ('Balkans','el','πλημμύρες καταιγίδα χαλάζι βίντεο'),
 ('Balkans','sr','poplave oluja sneg snimak'),
 ('Balkans','ro','inundații furtună ninsoare imagini'),
 ('Italy','it','alluvione grandine nubifragio video'),
 ('Spain','es','inundaciones granizo tormenta imágenes'),
 ('France','fr','inondations tempête grêle images'),
 ('India','hi','बाढ़ भारी बारिश वीडियो'),
 ('South Asia','en','cyclone flood landslide footage'),
 ('Latin America','es','inundaciones deslave tormenta video'),
 ('Southern Hemisphere','es','Patagonia temporal nieve inundación video'),
]

# Metadata screening only. None of these rules proves authenticity.
EXCLUDE = re.compile(
 r'animation|animated|cartoon|anime|minecraft|roblox|fortnite|gameplay|gaming|walkthrough|'
 r'film scene|movie scene|official trailer|ai.generated|made with ai|synthetic footage|'
 r'simulation|simulator|fictional|history of|historical documentary|explained history|'
 r'compilation of (?:old|historic)|top 10|top ten|reaction video|'
 r'ambient sounds|sleep music|relaxing music|study music|school lesson|exam prep|'
 r'dog relay|diphtheria|blizzard race|アニメ|ゲーム|动画|游戏|애니메이션|게임',re.I)
EVENT = re.compile(
 r'blizzard|snowstorm|whiteout|heavy snow|lake.effect snow|avalanche|flood|'
 r'tornado|waterspout|hurricane|typhoon|cyclone|landslide|mudslide|hailstorm|'
 r'severe thunderstorm|storm surge|flash flood|wildfire|'
 r'χιονοθύελλ|χιονόπτωσ|κακοκαιρ|πλημμύρ|ανεμοστρόβιλ|χαλάζ|καταιγίδ|'
 r'暴雪|吹雪|大雪|豪雨|洪水|台風|폭설|눈보라|폭우|홍수|'
 r'kar fırtınası|yoğun kar|sel baskını|hortum|dolu|'
 r'snöstorm|snøstorm|lumimyrsky|tulva|nevicata|alluvione|grandine|'
 r'schneesturm|hochwasser|lawine|inondation|tempête|grêle|'
 r'inundaciones|tormenta|granizo|poplave|furtună|inundații|बाढ़',re.I)
FOOTAGE = re.compile(
 r'footage|video|caught on camera|on camera|eyewitness|raw video|live report|'
 r'现场|映像|動画|현장|영상|görüntüleri|snimak|imagini|images|vídeo|video|'
 r'βίντεο|εικόνες|καρέ|ρεπορτάζ',re.I)
OLD = re.compile(
 r'\b(?:19\d\d|200\d|201\d|202[0-4])\b|'
 r'years ago|last decade|archive footage|archival footage|'
 r'from the archives|throwback|remembering|history of|historic blizzard|'
 r'old footage|previously recorded|十年前|過去の映像|昔の|옛날 영상',re.I)
SUSPICIOUS = re.compile(r'\b(?:ai|fake|generated|simulation|concept|cgi)\b',re.I)


def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json,application/rss+xml,*/*'})
    with urllib.request.urlopen(req,timeout=15) as response:
        return response.read()


def clean(value):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',value or ''))).strip()


def parse_date(value):
    if not value: return None
    try:
        p=email.utils.parsedate_to_datetime(value)
        return p.replace(tzinfo=UTC) if p.tzinfo is None else p.astimezone(UTC)
    except (TypeError,ValueError,OverflowError):
        try:
            p=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            return p.replace(tzinfo=UTC) if p.tzinfo is None else p.astimezone(UTC)
        except (AttributeError,TypeError,ValueError,OverflowError):
            return None


def key(platform,url):
    return hashlib.sha256((platform+'|'+url).encode()).hexdigest()[:20]


def assess(item):
    title=clean(item.get('title',''))
    published=parse_date(item.get('published_at'))
    age=(NOW-published).total_seconds()/3600 if published else 9999
    has_event=bool(EVENT.search(title))
    excluded=bool(EXCLUDE.search(title))
    historical=bool(OLD.search(title))
    suspicious=bool(SUSPICIOUS.search(title))
    footage=bool(FOOTAGE.search(title))
    score=0
    if has_event: score+=48
    if footage: score+=10
    if item.get('platform')=='YouTube': score+=10
    if 0<=age<=24: score+=24
    elif 0<=age<=48: score+=16
    elif 0<=age<=72: score+=8
    if historical: score-=60
    if suspicious: score-=35
    if excluded: score=0
    score=max(0,min(100,score))
    item['editorial_score']=score
    item['editorial_priority']='REVIEW' if excluded or historical or suspicious or not has_event else ('HOT' if score>=75 else 'NEW')
    reasons=[]
    if excluded: reasons.append('Metadata suggests unrelated or fictional content')
    if historical: reasons.append('Title suggests old footage or historical event')
    if suspicious: reasons.append('Possible synthetic/simulated content')
    if not has_event: reasons.append('No clear severe-weather event in title')
    reasons.append('Verify event date, location, original footage and reuse rights')
    item['review_reason']='; '.join(reasons)
    item['verified']=False
    return item


def make_item(platform,region,lang,query,title,url,published,source,thumbnail=''):
    item={'id':key(platform,url),'platform':platform,'region':region,'language':lang,
          'query':query,'title':clean(title),'url':url,'published_at':published,
          'found_at':NOW.isoformat(),'source':clean(source),'status':'new',
          'rights':'unknown','verified':False,'recorded_at':None,
          'notes':'Discovery only. Upload/publication time is not recording time.'}
    if thumbnail: item['thumbnail']=thumbnail
    return assess(item)


def rss_search(region,lang,query):
    params=urllib.parse.urlencode({'q':query+' when:2d','hl':'en-US','gl':'US','ceid':'US:en'})
    root=ET.fromstring(get('https://news.google.com/rss/search?'+params))
    out=[]
    for e in root.findall('.//channel/item')[:8]:
        title=clean(e.findtext('title'))
        url=e.findtext('link') or ''
        pub=parse_date(e.findtext('pubDate'))
        if not url or not pub or not 0<=(NOW-pub).total_seconds()<=72*3600: continue
        item=make_item('News RSS',region,lang,query,title,url,pub.isoformat(),e.findtext('source') or '')
        if item['editorial_priority']!='REVIEW': out.append(item)
    return out


def youtube_search(region,lang,query,api_key):
    params=urllib.parse.urlencode({'part':'snippet','q':query,'type':'video','order':'date',
       'maxResults':12,'publishedAfter':(NOW-dt.timedelta(days=3)).isoformat().replace('+00:00','Z'),
       'safeSearch':'moderate','key':api_key})
    data=json.loads(get('https://www.googleapis.com/youtube/v3/search?'+params))
    out=[]
    for e in data.get('items',[]):
        vid=e.get('id',{}).get('videoId')
        sn=e.get('snippet',{})
        if not vid: continue
        url='https://www.youtube.com/watch?v='+vid
        thumbs=sn.get('thumbnails',{})
        thumb=(thumbs.get('high') or thumbs.get('medium') or thumbs.get('default') or {}).get('url','')
        item=make_item('YouTube',region,lang,query,sn.get('title',''),url,
                       sn.get('publishedAt',''),sn.get('channelTitle',''),thumb)
        if item['editorial_priority']!='REVIEW': out.append(item)
    return out


def main():
    old=[]
    if DATA.exists():
        try: old=json.loads(DATA.read_text(encoding='utf-8')).get('items',[])
        except (OSError,ValueError,TypeError): pass
    # Retain only recent discoveries, and discard old REVIEW candidates.
    cutoff=NOW-dt.timedelta(days=5)
    found={}
    for entry in old:
        if not isinstance(entry,dict) or not entry.get('id'): continue
        if (parse_date(entry.get('found_at')) or dt.datetime.min.replace(tzinfo=UTC))<cutoff: continue
        entry=assess(entry)
        if entry['editorial_priority']!='REVIEW': found[entry['id']]=entry
    errors=[]
    new_count=0
    def fetch_rss(task):
        region,lang,query=task
        try: return rss_search(region,lang,query),None
        except Exception as exc: return [],f'RSS {region} {query}: {type(exc).__name__}: {str(exc)[:140]}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for results,error in pool.map(fetch_rss,QUERIES):
            if error: errors.append(error)
            for item in results:
                if item['id'] not in found: new_count+=1
                found[item['id']]=item
    api=os.environ.get('YOUTUBE_API_KEY','').strip()
    if api:
        # Rotate across three scheduled runs/day (05, 11, 17 UTC).
        slot=0 if NOW.hour<8 else 1 if NOW.hour<14 else 2
        start=((NOW.toordinal()*15)+(slot*5))%len(QUERIES)
        for i in range(5):
            region,lang,query=QUERIES[(start+i)%len(QUERIES)]
            try:
                for item in youtube_search(region,lang,query,api):
                    if item['id'] not in found: new_count+=1
                    found[item['id']]=item
            except Exception as exc:
                errors.append(f'YouTube {query}: {type(exc).__name__}: {str(exc)[:140]}')
    items=sorted(found.values(),key=lambda e:(e.get('editorial_score',0),e.get('published_at') or ''),reverse=True)[:400]
    DATA.parent.mkdir(parents=True,exist_ok=True)
    DATA.write_text(json.dumps({'updated_at':NOW.isoformat(),'count':len(items),
        'new_count':new_count,'youtube_enabled':bool(api),'errors':errors[:20],
        'items':items},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Items: {len(items)} | New: {new_count} | YouTube: {sum(e.get("platform")=="YouTube" for e in items)} | Errors: {len(errors)}')
    if errors: print('\n'.join(errors[:5]))

if __name__=='__main__':
    main()

