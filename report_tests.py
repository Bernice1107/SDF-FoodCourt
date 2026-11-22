import sqlite3, json
from pathlib import Path
from datetime import date, timedelta
import app as m
root=Path(__file__).resolve().parent
path=root/'report_artifacts'/'demo.db'
source=sqlite3.connect(root/'food_court.db'); target=sqlite3.connect(path)
source.backup(target); source.close()
target.execute('PRAGMA foreign_keys=ON')
for table in ['reviews','payments','paid_order_items','paid_orders','reservations','order_items','orders']:
    target.execute('DELETE FROM '+table)
target.commit(); target.close()
m.DATABASE=path
with m.app.app_context(): m.init_orders()
c=m.app.test_client(); man=m.app.test_client(); rival=m.app.test_client()
results=[]
def check(req, steps, expected, observed, ok):
    results.append({'req':req,'steps':steps,'expected':expected,'observed':observed,'result':'PASS' if ok else 'FAIL'})
    print(req,results[-1]['result'],observed)
def signin(client, identifier): client.post('/sign-in',data={'customer':identifier,'otp':'123456'})
def cart():
    c.post('/cart/add',data={'item_id':1})
    with c.session_transaction() as s: return s['checkout_token']
def order(token,service,payment,address=''):
    return c.post('/checkout',data={'checkout_token':token,'item_id':'1','quantity':'1','service':service,'payment':payment,'address':address},follow_redirects=True)
def booking(client, day, payment):
    client.get('/restaurants/1/book')
    with client.session_transaction() as s: token=s['booking_token']
    return client.post('/restaurants/1/book',data={'booking_token':token,'booking_date':day,'time_slot':'19:00','party_size':'6','payment':payment},follow_redirects=True)
signin(c,'student@example.com')
token=cart(); r=order(token,'Takeaway','success')
with sqlite3.connect(path) as db: row=db.execute('SELECT id,total_paise,order_status FROM paid_orders').fetchone()
check('FR8, FR9, FR10','Add dosa; confirm Takeaway success.','Paid order in history; total Rs 120.',f'Order #{row[0]} saved, {row[1]} paise, {row[2]}; history rendered.',r.status_code==200 and row[1]==12000 and b'Payment successful' in r.data)
token=cart(); r=order(token,'Takeaway','failure')
with c.session_transaction() as s: kept=s.get('cart')=={'1':1}
with sqlite3.connect(path) as db: count=db.execute('SELECT COUNT(*) FROM paid_orders').fetchone()[0]
check('FR8, FR9','Confirm demo payment decline.','Declined; cart retained; no new order.',f'Decline message; cart retained={kept}; orders={count}.',b'Payment declined' in r.data and kept and count==1)
r=order(token,'Delivery','success','  ')
with sqlite3.connect(path) as db: count=db.execute('SELECT COUNT(*) FROM paid_orders').fetchone()[0]
check('FR8, FR9','Select Delivery; submit blank address.','Address required; no new order.',f'Address validation message; orders={count}.',b'Enter a delivery address' in r.data and count==1)
day=(date.today()+timedelta(days=20)).isoformat(); r=booking(c,day,'success')
with sqlite3.connect(path) as db: rows=db.execute('SELECT COUNT(*),MAX(deposit_paise) FROM reservations').fetchone()
check('FR7, FR9, FR10','Book six seats at 19:00; deposit success.','Confirmed; deposit and history recorded.',f'{rows[0]} reservation; deposit {rows[1]} paise.',b'Demo deposit successful' in r.data and rows==(1,10000))
signin(rival,'demo@example.com'); r=booking(rival,day,'success')
check('FR7','Second customer books six seats at same slot.','No suitable table; selections retained.',f'Unavailable message; date {day} retained.',b'No suitable table' in r.data and day.encode() in r.data and b'value="6"' in r.data)
assert man.post('/manager/sign-in',data={'identifier':'curry.manager','password':'manager-demo'}).status_code==302
r=man.post(f'/manager/orders/{row[0]}/status',data={'status':'Ready for Pickup'},follow_redirects=True)
with sqlite3.connect(path) as db: status=db.execute('SELECT order_status FROM paid_orders WHERE id=?',(row[0],)).fetchone()[0]
check('FR8, FR10','Manager marks Takeaway Ready for Pickup.','Status updated and shown in history.',f'Status={status}; history contains status.',status=='Ready for Pickup' and b'Ready for Pickup' in c.get('/history').data)
customer_status=c.get('/manager').status_code
other=m.app.test_client(); other.post('/manager/sign-in',data={'identifier':'copper.manager','password':'manager-demo'}); other_status=other.post(f'/manager/orders/{row[0]}/status',data={'status':'Completed'}).status_code
check('FR1, FR8','Customer opens manager; other manager updates order.','Customer 403; other restaurant denied.',f'Customer HTTP {customer_status}; other manager HTTP {other_status}.',customer_status==403 and other_status==404)
man.post(f'/manager/orders/{row[0]}/status',data={'status':'Completed'})
r1=c.post(f'/orders/{row[0]}/review',data={'rating':'5','review':'Tasty and fresh.'},follow_redirects=True)
r2=c.post(f'/orders/{row[0]}/review',data={'rating':'4','review':'Again'},follow_redirects=True)
with sqlite3.connect(path) as db: reviews=db.execute('SELECT COUNT(*) FROM reviews WHERE order_id=?',(row[0],)).fetchone()[0]
check('FR5','Complete order; submit review twice.','First saved; duplicate rejected.',f'First saved; duplicate message; {reviews} review row.',b'Your review was saved' in r1.data and b'already has a review' in r2.data and reviews==1)
(root/'report_artifacts'/'test_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
assert all(x['result']=='PASS' for x in results)
