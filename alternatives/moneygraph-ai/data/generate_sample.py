from datetime import datetime, timedelta, timezone
import csv
from pathlib import Path

def create():
    rows=[]
    start=datetime(2026,9,1,9,tzinfo=timezone.utc)
    def add(a,b,amount,minutes):
        rows.append([a,b,amount,(start+timedelta(minutes=minutes)).isoformat()])
    # Synthetic planted structures. 44 accounts, no real identities.
    for day in range(4):
        base=day*1440
        for i in range(1,13):
            add(f'A{i:02}','D' if i<=6 else 'E',10000+i*500,base+i)
        add('D','F',70000,base+20)
        add('E','F',85000,base+24)
        for i in range(1,7):
            add(f'B{i:02}','F',6000+i*500,base+25+i)
        add('F','X',130000,base+40)
        add('F','Y',40000,base+42)
        add('F','Z',35000,base+45)
        for i in range(1,7):
            add('X',f'C{i:02}',20000,base+50+i)
        for i in range(1,13):
            add(f'N{i:02}',f'N{(i%12)+1:02}',800+((i*137+day*83)%1700),base+100+i*17)
        add('N03','B01',1200,base+500)
        add('C06','N07',1800,base+700)
    path=Path(__file__).resolve().parent/'sample_transactions.csv'
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f)
        writer.writerow(['sender','receiver','amount','timestamp'])
        writer.writerows(rows)
    print(f'{len(rows)} transactions, {len({v for r in rows for v in r[:2]})} accounts')
if __name__=='__main__':
    create()
