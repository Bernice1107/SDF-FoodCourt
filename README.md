# Food Court: Food & Drinks

Food Court is a web app for browsing fictional restaurants and menus. Filter by locality, cuisine, or food preference to see matching restaurants and menu items. Selecting all localities shows results from both. No login is needed to browse


## Start on Windows (PowerShell)

From this project folder, with Python 3.10 or newer installed:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe -m flask --app app run
```

Open http://127.0.0.1:5000/ in a browser. Stop the server with Ctrl+C. Run the seed command again whenever needed: existing restaurant names and restaurant/menu-item pairs are retained without duplicates. It does not overwrite existing records.

If Windows application control blocks the virtual environment executable on this computer, this session used the already-installed interpreter and Flask packages from another local project:

```powershell
$env:PYTHONPATH = 'C:\Users\Bernice\DellBackup\Projects\.venv\Lib\site-packages'
& 'C:\Users\Bernice\AppData\Roaming\uv\python\cpython-3.12.15-windows-x86_64-none\python.exe' seed.py
& 'C:\Users\Bernice\AppData\Roaming\uv\python\cpython-3.12.15-windows-x86_64-none\python.exe' -m flask --app app run --no-reload
```

That fallback depends on those existing paths. If application control also blocks a Python DLL, retry or use an approved Python installation.

## Follow one request

1. Open the page in Chrome or Edge. Press F12, select **Network**, and select **Fetch/XHR**. If needed, reload the page.
2. Choose **Malleswaram**, **South Indian**, and **Veg**. Click the latest `restaurants?...` request. In **Headers**, inspect the Request URL: `/api/restaurants?locality=Malleswaram&cuisine=South+Indian&preference=Veg` (the host and parameter encoding appear in the full URL).
3. In `static/app.js`, follow `loadRestaurants()`: it builds the query parameters and calls `fetch()`. In `app.py`, follow the `/api/restaurants` route and `restaurants()` function to the parameterized `SELECT` joining restaurants and menu items.
4. In the request's **Response** tab, inspect the JSON array: Curry Leaf Kitchen contains Masala Dosa. Back in `loadRestaurants()`, `response.json()` reads it and the `forEach` loops create and append the restaurant card and menu rows to `#restaurants` in `templates/index.html`.
5. To see the empty message, select Indiranagar and North Indian. To see the error message, stop Flask and then change a filter; restart Flask to continue. The loading message appears while a request is pending; use Network throttling (for example, Slow 3G) if it passes too quickly to see.

## Demo cart and checkout

Add items from one restaurant, adjust quantities or remove them in the cart. The demo sign-in accepts the seeded users `student@example.com` and `demo@example.com` and the displayed OTP `123456`; it does not send a real OTP. The signed session keeps the cart through sign-in. Demo identities are not verified and this is not a production authentication or payment system.

At checkout, choose Takeaway or Delivery and select **Update total** to see the server-calculated fee and total. Sign in before confirming. Delivery requires an address. Choose simulated success or decline; decline keeps the cart, while success saves the order and its price snapshots in My History for the same demo identifier. Delivery costs ₹40 in this demonstration. Flask reads prices from SQLite when confirming; it does not accept a total from the browser. Totals and order price snapshots are stored as integer paise. The existing menu prices are stored in whole rupees and converted to paise on lookup. A unique checkout token prevents repeat paid orders.

## Dine-in reservations

Select **Book a table** on a restaurant and sign in with a seeded demo user. Choose today or a future date, a fixed time slot, and a party size from 1 to 6. Each restaurant has one table each for 2, 4, and 6 people. The app assigns the smallest suitable available table. The displayed deposit is a simulated payment; a decline does not reserve a table. Confirmed bookings and deposit amounts appear in My History. SQLite prevents the same table being reserved twice for the same date and time slot.

## Manager, offers and reviews

Use **Manager** in the navigation. The separate classroom manager IDs are `curry.manager` (Curry Leaf Kitchen) and `copper.manager` (Copper Spoon), with demo password `manager-demo`. Customer OTP `123456` does not sign in a manager. Sign out using **Manager sign out**. This is classroom authentication, not secure production identity verification. A manager sees and changes only the assigned restaurant's records. Order transitions are Placed -> Ready for Pickup -> Completed for Takeaway, and Placed -> Out for Delivery -> Completed for Delivery. Reservations transition Confirmed -> Checked In -> Completed. Existing paid orders and reservations retain their data and initially receive Placed and Confirmed statuses respectively; older legacy orders remain in history but cannot be progressed or reviewed because they lack the newer account and restaurant links.

Restaurant cards and **View offers & reviews** show active seeded offer information and ratings. Offer text is informational and is not automatically applied to checkout. A customer may submit one rating and review per completed, eligible order from My History. The application checks ownership and status; SQLite enforces one review per order.
