#!/usr/bin/env python3
"""Dokari Weather Radar: public news and YouTube discovery, not verification."""
import concurrent.futures
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'docs' / 'data.json'
UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)
QUERIES = [
 ('Turkey','tr','Bolu yoğun kar yağışı'),('Turkey','tr','Kartalkaya kar fırtınası'),
 ('Turkey','tr','Erzurum tipi kar'),('Japan','ja','札幌 大雪 動画'),
 ('Japan','ja','北海道 吹雪'),('Japan','ja','青森 大雪'),
 ('Nordics','en','Norway snowstorm video'),('Nordics','sv','Sverige snöstorm'),
 ('Nordics','fi','Suomi lumimyrsky'),('Alps','it','nevicata intensa Dolomiti video'),
 ('Alps','de','Schneesturm Alpen Video'),('USA','en','Buffalo lake effect snow video'),
 ('USA','en','blizzard winter storm footage'),('Alaska','en','Alaska blizzard snow'),
 ('Canada','en','Quebec snowstorm video'),('Canada','en','Newfoundland blizzard'),
 ('Greenland','en','Greenland blizzard snowstorm'),('Asia','ko','한국 폭설 영상'),
 ('Asia','zh','暴雪 视频'),('Balkans','el','χιονόπτωση κακοκαιρία βίντεο'),
 ('Southern Hemisphere','en','Patagonia snowstorm video')
]
USER_AGENT = 'DokariWeatherRadar/2.0 (public editorial discovery)'
# Conservative exclusion: flags based on metadata, never asserts footage authenticity.
EXCLUDE = re.compile(r'\b(animation|animated|cartoon|anime|minecraft|roblox|fortnite|gameplay|gaming|walkthrough|trailer|movie|film scene|ai generated|ai-generated|made with ai|mid.term|midterm|exam|test lessons|quiz|fictional|simulation|simulator|dog relay|dog ran 600 miles)\b|애니메이션|게임|중간평가|시험|アニメ|ゲーム|动画|游戏', re.I)
STRONG = re.compile(r'blizzard|snowstorm|whiteout|heavy snow|lake.effect|avalanche|flood|tornado|extreme weather|storm surge|χιονοθύελλ|χιονόπτωσ|κακοκαιρ|暴雪|吹雪|大雪|폭설|눈보라|kar fırtınası|yoğun kar|tipi kar|snöstorm|lumimyrsky|nevicata intensa|schneesturm', re.I)
WEAK = re.compile(r'\bsnow\b|winter|weather|χιον|雪|눈|kar|snö|lumi|neve|schnee', re.I)

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/rss+xml,application/json,*/*'})
    with urllib.request.urlopen(req, timeout=12) as response:
        return response.read()

def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()

def parse_date(value):
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None

def key(platform, url):
    return hashlib.sha256((platform + '|' + url).encode()).hexdigest()[:20]

def assess(item):
    title = item.get('title', '')
    published = parse_date(item.get('published_at'))
    age_hours = (NOW - published).total_seconds()/3600 if published else 999
    excluded = bool(EXCLUDE.search(title))
    strong = bool(STRONG.search(title))
    weak = bool(WEAK.search(title))
    score = (45 if strong else 12 if weak else 0) + (25 if age_hours <= 24 else 15 if age_hours <= 48 else 0)
    score += 10 if item.get('platform') == 'YouTube' else 0
    if excluded: score = 0
    item['editorial_score'] = min(score, 100)
    item['editorial_priority'] = 'REVIEW' if excluded or not (strong or weak) else 'HOT' if score >= 70 else 'NEW'
    item['review_reason'] = 'Potentially unrelated/synthetic/fictional metadata; manual review' if excluded else 'Confirm recording date, location, authenticity and reuse permission'
    item['verified'] = False
    return item

def rss_search(region, lang, query):
    params = urllib.parse.urlencode({'q': query+' when:2d', 'hl':'en-US','gl':'US','ceid':'US:en'})
    root = ET.fromstring(get('https://news.google.com/rss/search?' + params))
    output=[]
    for entry in root.findall('.//channel/item')[:8]:
        title=clean(entry.findtext('title'))
        url=entry.findtext('link') or ''
        published=parse_date(entry.findtext('pubDate'))
        if not url or not published or (NOW-published).total_seconds()>72*3600: continue
        output.append(assess({'id':key('News RSS',url),'platform':'News RSS','region':region,'language':lang,'query':query,'title':title,'url':url,'published_at':published.isoformat(),'found_at':NOW.isoformat(),'source':clean(entry.findtext('source')),'status':'new','rights':'unknown','verified':False,'recorded_at':None,'notes':'News article, not necessarily a video. Confirm original footage.'}))
    return output

def youtube_search(region, lang, query, api_key):
    params=urllib.parse.urlencode({'part':'snippet','q':query,'type':'video','order':'date','maxResults':8,'publishedAfter':(NOW-dt.timedelta(days=2)).isoformat().replace('+00:00','Z'),'key':api_key})
    data=json.loads(get('https://www.googleapis.com/youtube/v3/search?' + params))
    output=[]
    for entry in data.get('items',[]):
        vid=entry.get('id',{}).get('videoId')
        sn=entry.get('snippet',{})
        if not vid: continue
        url='https://www.youtube.com/watch?v='+vid
        output.append(assess({'id':key('YouTube',url),'platform':'YouTube','region':region,'language':lang,'query':query,'title':clean(sn.get('title')),'url':url,'published_at':sn.get('publishedAt'),'found_at':NOW.isoformat(),'source':sn.get('channelTitle',''),'thumbnail':sn.get('thumbnails',{}).get('medium',{}).get('url',''),'status':'new','rights':'unknown','verified':False,'recorded_at':None,'notes':'Upload date is not filming date. Review original footage and rights.'}))
    return output

def main():
    old=[]
    if DATA.exists():
        try: old=json.loads(DATA.read_text(encoding='utf-8')).get('items',[])
        except (OSError,ValueError): pass
    found={entry['id']:assess(entry) for entry in old if entry.get('id')}
    errors=[]
    new_count=0
    def fetch_rss(task):
        region,lang,query=task
        try: return rss_search(region,lang,query),None
        except Exception as exc: return [],f'RSS {region} {query}: {type(exc).__name__}: {str(exc)[:160]}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for results,error in pool.map(fetch_rss,QUERIES):
            if error: errors.append(error)
            for entry in results:
                if entry['id'] not in found: new_count+=1
                found[entry['id']]=entry
    api=os.environ.get('YOUTUBE_API_KEY','').strip()
    if api:
        # Five searches per run, rotate daily and across three daily runs.
        # search.list costs 100 units/request; scheduled 3x/day ~1500 units/day.
        slot=min(NOW.hour//6,3)
        start=((NOW.timetuple().tm_yday*15)+(slot*5))%len(QUERIES)
        for i in range(5):
            region,lang,query=QUERIES[(start+i)%len(QUERIES)]
            try:
                for entry in youtube_search(region,lang,query,api):
                    if entry['id'] not in found: new_count+=1
                    found[entry['id']]=entry
            except Exception as exc: errors.append(f'YouTube {query}: {type(exc).__name__}: {str(exc)[:160]}')
    cutoff=NOW-dt.timedelta(days=14)
    items=[entry for entry in found.values() if (parse_date(entry.get('found_at')) or NOW)>=cutoff]
    # Keep review items visible (not silently deleted) but rank lower.
    items.sort(key=lambda entry:(entry.get('editorial_score',0),entry.get('published_at') or ''),reverse=True)
    items=items[:600]
    DATA.parent.mkdir(parents=True,exist_ok=True)
    DATA.write_text(json.dumps({'updated_at':NOW.isoformat(),'count':len(items),'new_count':new_count,'youtube_enabled':bool(api),'errors':errors[:20],'items':items},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Items: {len(items)} | New: {new_count} | YouTube: {sum(x.get("platform")=="YouTube" for x in items)} | Errors: {len(errors)}')
    if errors: print('\n'.join(errors[:5]))

if __name__=='__main__':
    main()
