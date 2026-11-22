#!/usr/bin/env python3
"""Zero-cost discovery from public Google News RSS and optional YouTube API.
No scraping of Facebook/Instagram or video downloads.
"""
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
USER_AGENT='DokariWeatherRadar/1.0 (+editorial discovery; public RSS)'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/rss+xml,application/json,*/*'})
    with urllib.request.urlopen(req,timeout=7) as r: return r.read()

def clean(s):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',s or ''))).strip()

def parse_date(s):
    try: return email.utils.parsedate_to_datetime(s).astimezone(UTC)
    except (TypeError,ValueError,OverflowError):
        try: return dt.datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(UTC)
        except (AttributeError,TypeError,ValueError): return None

def key(platform,url): return hashlib.sha256((platform+'|'+url).encode()).hexdigest()[:20]

def rss_search(region,lang,query):
    params=urllib.parse.urlencode({'q':query+' when:2d','hl':'en-US','gl':'US','ceid':'US:en'})
    url='https://news.google.com/rss/search?'+params
    root=ET.fromstring(get(url))
    out=[]
    for item in root.findall('.//channel/item')[:8]:
        title=clean(item.findtext('title'))
        link=item.findtext('link') or ''
        published=parse_date(item.findtext('pubDate'))
        if not link or not published or (NOW-published).total_seconds()>60*60*72: continue
        out.append({'id':key('News RSS',link),'platform':'News RSS','region':region,'language':lang,'query':query,'title':title,'url':link,'published_at':published.isoformat(),'found_at':NOW.isoformat(),'source':clean(item.findtext('source')),'status':'new','rights':'unknown','verified':False,'recorded_at':None,'notes':'Article discovery; may contain embedded social video. Check original media and recording date.'})
    return out

def youtube_search(region,lang,query,api_key):
    params=urllib.parse.urlencode({'part':'snippet','q':query,'type':'video','order':'date','maxResults':8,'publishedAfter':(NOW-dt.timedelta(days=2)).isoformat().replace('+00:00','Z'),'key':api_key})
    data=json.loads(get('https://www.googleapis.com/youtube/v3/search?'+params))
    out=[]
    for item in data.get('items',[]):
        vid=item.get('id',{}).get('videoId')
        sn=item.get('snippet',{})
        if not vid: continue
        url='https://www.youtube.com/watch?v='+vid
        out.append({'id':key('YouTube',url),'platform':'YouTube','region':region,'language':lang,'query':query,'title':clean(sn.get('title')),'url':url,'published_at':sn.get('publishedAt'),'found_at':NOW.isoformat(),'source':sn.get('channelTitle',''),'thumbnail':sn.get('thumbnails',{}).get('medium',{}).get('url',''),'status':'new','rights':'unknown','verified':False,'recorded_at':None,'notes':'Upload date is not recording date. Verify location, time, footage and permissions.'})
    return out

def main():
    old=[]
    if DATA.exists():
        try: old=json.loads(DATA.read_text(encoding='utf-8')).get('items',[])
        except (OSError,ValueError): pass
    found={x['id']:x for x in old if x.get('id')}
    errors=[]; n=0
    def fetch_rss(task):
        region,lang,query=task
        try: return rss_search(region,lang,query),None
        except Exception as e: return [],f'RSS {region} {query}: {type(e).__name__}: {str(e)[:160]}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for results,error in pool.map(fetch_rss,QUERIES):
            if error: errors.append(error)
            for x in results:
                if x['id'] not in found: found[x['id']]=x;n+=1
    api=os.environ.get('YOUTUBE_API_KEY','').strip()
    if api:
        # 5 search requests per run to stay within typical default daily quota
        # with 3 scheduled runs per day (15 x 100 units = 1500/day).
        day_index=NOW.timetuple().tm_yday
        for i in range(5):
            region,lang,query=QUERIES[(day_index*5 + i)%len(QUERIES)]
            try:
                for x in youtube_search(region,lang,query,api):
                    if x['id'] not in found: found[x['id']]=x;n+=1
            except Exception as e: errors.append(f'YouTube {query}: {type(e).__name__}: {str(e)[:160]}')
    # Keep last 14 days of discovery and max 600 items
    cutoff=NOW-dt.timedelta(days=14)
    items=sorted((x for x in found.values() if (parse_date(x.get('found_at')) or NOW)>=cutoff),key=lambda x:x.get('published_at') or '',reverse=True)[:600]
    DATA.parent.mkdir(parents=True,exist_ok=True)
    DATA.write_text(json.dumps({'updated_at':NOW.isoformat(),'count':len(items),'new_count':n,'youtube_enabled':bool(api),'errors':errors[:20],'items':items},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Items: {len(items)} | New: {n} | Errors: {len(errors)}')
    if errors: print('\n'.join(errors[:5]))

if __name__=='__main__':main()
