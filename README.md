# Steps to Finish the Minimal Last-Mile Delivery Management System

Based on your progress report, here is a step-by-step plan to build a minimal working version of your application. This focuses on getting a functional end-to-end system rather than a polished product.

---

## Phase 1: Data Preparation (Week 4)

### Step 1: Download & Inspect the Dataset
- Download the Jilin delivery dataset from the Hugging Face link.
- Load it into a Python environment (pandas) or a notebook.
- Inspect columns: `order_id`, `courier_id`, `aoi_id`, `aoi_type`, `region_id`, `city`, `accept_time`, `delivery_time`, `lng`, `lat`, GPS timestamps, etc.

### Step 2: Clean & Preprocess
- Handle missing values (drop or impute).
- Convert timestamps to a consistent format.
- Remove duplicates.
- Derive useful fields:
  - `delivery_duration` = `delivery_time` - `accept_time`
  - `is_delayed` = 1 if duration > threshold (e.g., 2 hours), else 0
- Split data into:
  - **Structured tables** for SQL (Region, Courier, Order, AOI, Courier_AOI, Acceptance_Location, Delivery_Location)
  - **Flexible event documents** for MongoDB (delivery events, GPS tracking logs)

### Step 3: Export Data
- Save cleaned CSVs for SQL import.
- Save JSON/BSON files for MongoDB import.

---

## Phase 2: Database Design & Setup (Weeks 5–6)

### Step 4: Finalize the ERD
- Use the ERD from your report (Page 5) as the blueprint.
- Confirm all relationships:
  - Region 1:M Courier
  - Courier 1:M Order
  - Courier M:M AOI (via Courier_AOI)
  - Order 1:1 Acceptance_Location
  - Order 1:1 Delivery_Location
  - AOI 1:M Courier_AOI

### Step 5: Create the SQL Database
- Choose a DBMS (MySQL, PostgreSQL, or SQLite for simplicity).
- Write `CREATE TABLE` statements for:
  - `REGION`, `COURIER`, `ORDER`, `AOI`, `COURIER_AOI`, `ACCEPTANCE_LOCATION`, `DELIVERY_LOCATION`
- Define primary keys, foreign keys, and constraints.
- Bulk insert cleaned CSV data.

### Step 6: Design MongoDB Collections
- Create collections:
  - `delivery_events`: `{ order_id, courier_id, event_type, timestamp, location: { lng, lat } }`
  - `tracking_logs`: `{ order_id, courier_id, gps_points: [ { lng, lat, timestamp } ] }`
- Insert corresponding data from the dataset.

---

## Phase 3: Backend Development (Weeks 7–9)

### Step 7: Choose a Backend Stack
- Recommended: **Node.js + Express** or **Python + Flask/FastAPI**.
- Install drivers:
  - SQL: `mysql2`, `psycopg2`, or `sqlite3`
  - MongoDB: `mongodb` or `pymongo`

### Step 8: Implement Core API Endpoints
Minimal set:

| Functionality | Endpoint | Method |
|---|---|---|
| List orders | `/orders` | GET |
| Get order details | `/orders/:id` | GET |
| Create order | `/orders` | POST |
| Update order | `/orders/:id` | PUT |
| Delete order | `/orders/:id` | DELETE |
| List couriers | `/couriers` | GET |
| Orders by courier | `/couriers/:id/orders` | GET |
| Track order (SQL) | `/orders/:id/tracking` | GET |
| Track order (MongoDB) | `/orders/:id/events` | GET |
| Delivery stats | `/analytics/delivery-time` | GET |
| Courier performance | `/analytics/courier-performance` | GET |
| Delay detection | `/analytics/delayed-orders` | GET |

### Step 9: Connect to Both Databases
- SQL connection pool for structured queries.
- MongoDB client for event/tracking queries.
- Ensure both are used in the same backend service.

### Step 10: Implement SQL vs NoSQL Comparison
- For selected operations (e.g., "get tracking history for an order"), implement two versions:
  - SQL: JOIN across `ORDER`, `ACCEPTANCE_LOCATION`, `DELIVERY_LOCATION`
  - MongoDB: Query `tracking_logs` collection
- Log execution time for each and expose via an endpoint like `/compare/tracking/:id`.

---

## Phase 4: Frontend Development (Weeks 9–11)

### Step 11: Choose a Frontend Stack
- Recommended: **React** (with Vite) or plain HTML/JS + Bootstrap.
- Keep it minimal: a few pages/components.

### Step 12: Build Core UI Pages
1. **Order Management**
   - Table of orders with CRUD buttons.
   - Form to create/edit an order.
2. **Courier Management**
   - List couriers.
   - View orders assigned to a courier.
3. **Delivery Tracking**
   - Search by order ID.
   - Display acceptance/delivery times and GPS on a map (Leaflet or Google Maps).
4. **Analytics Dashboard**
   - Average delivery time.
   - Number of deliveries per courier.
   - List of delayed orders.
   - SQL vs NoSQL query time comparison.

### Step 13: Connect Frontend to Backend
- Use `fetch` or `axios` to call API endpoints.
- Handle loading and error states minimally.

---

## Phase 5: Testing & Analysis (Weeks 10–12)

### Step 14: Test the System
- Unit test API endpoints (Postman or Jest/Pytest).
- Test with small sample first, then larger dataset.
- Verify CRUD operations, tracking, and analytics.

### Step 15: Run SQL vs NoSQL Comparison
- Execute the same queries on both databases.
- Record:
  - Query execution time
  - Ease of writing query
  - Schema flexibility
- Summarize findings for your report.

### Step 16: Evaluate Performance
- Measure response times for key endpoints.
- Identify bottlenecks (e.g., missing indexes).
- Add indexes on frequently queried columns/fields.

---

## Phase 6: Documentation & Presentation (Weeks 12–13)

### Step 17: Finalize Report
- Update progress report with:
  - Final ERD
  - Screenshots of UI
  - SQL vs NoSQL comparison results
  - Challenges faced and solutions

### Step 18: Prepare Presentation
- Demo the working system.
- Highlight:
  - Architecture
  - Key functionalities
  - SQL vs NoSQL findings
  - Lessons learned

---

## Minimal Viable Product (MVP) Checklist

To call it "done" minimally, you need:

- [ ] Cleaned dataset loaded into SQL and MongoDB
- [ ] SQL tables created and populated
- [ ] MongoDB collections created and populated
- [ ] Backend with at least: order CRUD, courier list, tracking, one analytics endpoint
- [ ] Frontend with at least: order list, order detail/tracking, analytics view
- [ ] One SQL vs NoSQL comparison query with timing
- [ ] Basic testing done
- [ ] Report and presentation ready

---

## Suggested Tech Stack (Minimal)

| Layer | Recommendation |
|---|---|
| SQL DB | SQLite (easiest) or MySQL |
| NoSQL DB | MongoDB (local or Atlas free tier) |
| Backend | Python Flask or Node.js Express |
| Frontend | React (Vite) or plain HTML + Bootstrap |
| Maps | Leaflet (free) |
| Testing | Postman + Pytest/Jest |

---

## Time Estimate

| Phase | Weeks | Focus |
|---|---|---|
| Data Prep | 4 | Clean, split, export |
| DB Design | 5–6 | ERD, SQL, MongoDB |
| Backend | 7–9 | APIs, DB connections |
| Frontend | 9–11 | UI pages |
| Testing & Analysis | 10–12 | Compare SQL/NoSQL |
| Report & Presentation | 12–13 | Documentation |

This plan aligns with your Gantt chart and gets you to a working minimal application by Week 12–13.
