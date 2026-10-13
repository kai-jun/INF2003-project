const state = {
  orders: [],
  couriers: [],
  filteredOrders: [],
  orderPage: 1,
  pageSize: 25,
  editingOrderId: null,
};
let trackingMap = null;
let trackingMarkers = null;

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail || `Request failed (${response.status})`);
  }
  return payload;
}

function showAlert(message) {
  const alert = byId("apiAlert");
  alert.textContent = message;
  alert.classList.remove("d-none");
  setApiStatus("Needs attention", "error");
}

function clearAlert() {
  byId("apiAlert").classList.add("d-none");
  byId("apiAlert").textContent = "";
}

function setApiStatus(label, status) {
  const indicator = byId("apiStatus");
  indicator.classList.remove("is-pending", "is-error");
  if (status === "pending") indicator.classList.add("is-pending");
  if (status === "error") indicator.classList.add("is-error");
  indicator.querySelector("span").textContent = label;
}

function showView(viewName) {
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${viewName}View`);
  });
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    if (button.classList.contains("nav-link")) {
      button.classList.toggle("active", button.dataset.viewTarget === viewName);
    }
  });
  const sectionTitle = {
    overview: "Overview", orders: "Orders", couriers: "Couriers", tracking: "Tracking compare",
  }[viewName] || "Overview";
  byId("currentSection").textContent = sectionTitle;
  clearAlert();
}

function formatDuration(value) {
  return value == null ? "-" : `${Number(value).toFixed(2)} hrs`;
}

function formatTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ");
}

function orderActions(orderId) {
  const safeId = escapeHtml(orderId);
  return `<div class="row-actions">
    <button class="icon-button" type="button" data-action="track" data-id="${safeId}" title="Compare tracking" aria-label="Compare tracking"><i class="bi bi-signpost-2"></i></button>
    <button class="icon-button" type="button" data-action="edit" data-id="${safeId}" title="Edit order" aria-label="Edit order"><i class="bi bi-pencil"></i></button>
    <button class="icon-button danger" type="button" data-action="delete" data-id="${safeId}" title="Delete order" aria-label="Delete order"><i class="bi bi-trash3"></i></button>
  </div>`;
}

function renderOrders() {
  const query = byId("orderSearch").value.trim().toLowerCase();
  state.filteredOrders = state.orders.filter((order) =>
    String(order.order_id).toLowerCase().includes(query)
    || String(order.courier_id ?? "").toLowerCase().includes(query),
  );
  const totalPages = Math.max(1, Math.ceil(state.filteredOrders.length / state.pageSize));
  state.orderPage = Math.min(state.orderPage, totalPages);
  const start = (state.orderPage - 1) * state.pageSize;
  const visible = state.filteredOrders.slice(start, start + state.pageSize);
  byId("orderTableCount").textContent = `${state.filteredOrders.length.toLocaleString()} orders`;
  byId("navOrderCount").textContent = state.orders.length.toLocaleString();
  byId("pageSummary").textContent = state.filteredOrders.length
    ? `${(start + 1).toLocaleString()}-${Math.min(start + state.pageSize, state.filteredOrders.length).toLocaleString()} of ${state.filteredOrders.length.toLocaleString()}`
    : "No matching orders";
  byId("previousPage").disabled = state.orderPage <= 1;
  byId("nextPage").disabled = state.orderPage >= totalPages;
  if (!visible.length) {
    byId("orderRows").innerHTML = '<tr><td colspan="7" class="empty-cell">No orders match this search.</td></tr>';
    return;
  }
  byId("orderRows").innerHTML = visible.map((order) => `<tr>
    <td><span class="id-text">${escapeHtml(order.order_id)}</span></td>
    <td><span class="mono-text">${escapeHtml(order.courier_id || "-")}</span></td>
    <td>${escapeHtml(formatTime(order.accept_time))}</td>
    <td>${escapeHtml(formatTime(order.delivery_time))}</td>
    <td>${escapeHtml(formatDuration(order.delivery_duration_hours))}</td>
    <td>${escapeHtml(order.ds || "-")}</td>
    <td>${orderActions(order.order_id)}</td>
  </tr>`).join("");
}

function renderCouriers() {
  byId("courierCount").textContent = `${state.couriers.length.toLocaleString()} total`;
  if (!state.couriers.length) {
    byId("courierRows").innerHTML = '<tr><td colspan="3" class="empty-cell">No couriers found.</td></tr>';
    return;
  }
  byId("courierRows").innerHTML = state.couriers.map((courier) => `<tr>
    <td><span class="id-text">${escapeHtml(courier.courier_id)}</span></td>
    <td>${escapeHtml(courier.region_id ?? "-")}</td>
    <td><div class="row-actions"><button class="icon-button" type="button" data-action="courier-orders" data-id="${escapeHtml(courier.courier_id)}" title="View courier orders" aria-label="View courier orders"><i class="bi bi-arrow-right"></i></button></div></td>
  </tr>`).join("");
}

function renderCourierPerformance(rows) {
  const target = byId("overviewCourierRows");
  if (!rows?.length) {
    target.innerHTML = '<tr><td colspan="4" class="empty-cell">No performance data available.</td></tr>';
    return;
  }
  target.innerHTML = rows.map((row) => `<tr>
    <td><span class="id-text">${escapeHtml(row.courier_id)}</span></td>
    <td>${Number(row.order_count || 0).toLocaleString()}</td>
    <td>${escapeHtml(formatDuration(row.avg_delivery_hours))}</td>
    <td><div class="row-actions"><button class="icon-button" type="button" data-action="courier-orders" data-id="${escapeHtml(row.courier_id)}" title="View courier orders" aria-label="View courier orders"><i class="bi bi-arrow-right"></i></button></div></td>
  </tr>`).join("");
}

function renderDelayedOrders(orders) {
  byId("delayedOrderCount").textContent = `${orders.length.toLocaleString()} flagged`;
  const target = byId("delayedOrderRows");
  if (!orders.length) {
    target.innerHTML = '<tr><td colspan="6" class="empty-cell">No delayed orders found.</td></tr>';
    return;
  }
  target.innerHTML = orders.map((order) => `<tr>
    <td><span class="id-text">${escapeHtml(order.order_id)}</span></td>
    <td><span class="mono-text">${escapeHtml(order.courier_id || "-")}</span></td>
    <td>${escapeHtml(order.aoi_id || "-")}</td>
    <td>${escapeHtml(formatTime(order.accept_time))}</td>
    <td>${escapeHtml(formatTime(order.delivery_time))}</td>
    <td><div class="row-actions"><button class="icon-button" type="button" data-action="track" data-id="${escapeHtml(order.order_id)}" title="Compare tracking" aria-label="Compare tracking"><i class="bi bi-signpost-2"></i></button></div></td>
  </tr>`).join("");
}

function renderCourierOrders(courierId, orders) {
  byId("courierOrdersTitle").textContent = `Courier ${courierId}`;
  byId("courierOrdersCount").textContent = `${orders.length.toLocaleString()} orders`;
  if (!orders.length) {
    byId("courierOrdersBody").innerHTML = '<div class="detail-empty"><i class="bi bi-inbox"></i><span>No assigned orders found.</span></div>';
    return;
  }
  byId("courierOrdersBody").innerHTML = `<div class="detail-order-list">${orders.slice(0, 60).map((order) => `<div class="detail-order-row"><span class="id-text">${escapeHtml(order.order_id)}</span><span class="mono-text">${escapeHtml(formatDuration(order.delivery_duration_hours))}</span></div>`).join("")}</div>`;
}

function eventMarkup(type, timestamp, latitude, longitude) {
  const coordinates = latitude == null || longitude == null ? "Coordinates unavailable" : `${latitude}, ${longitude}`;
  return `<div class="event-row"><span class="event-type">${escapeHtml(type || "event")}</span><div class="event-detail"><time>${escapeHtml(formatTime(timestamp))}</time><span>${escapeHtml(coordinates)}</span></div></div>`;
}

function renderSqlTracking(rows) {
  const target = byId("sqlTrackingBody");
  const events = [];
  rows.forEach((row) => {
    if (row.accept_timestamp) events.push(eventMarkup("accept", row.accept_timestamp, row.accept_latitude, row.accept_longitude));
    if (row.delivery_timestamp) events.push(eventMarkup("delivery", row.delivery_timestamp, row.delivery_latitude, row.delivery_longitude));
  });
  target.innerHTML = events.length ? events.join("") : '<div class="detail-empty">No SQL location rows found.</div>';
}

function renderMongoTracking(rows) {
  const target = byId("mongoTrackingBody");
  target.innerHTML = rows.length
    ? rows.map((event) => eventMarkup(event.event_type, event.timestamp, event.lat, event.lng)).join("")
    : '<div class="detail-empty">No MongoDB tracking events found.</div>';
}

function renderTrackingMap(sqlRows, mongoRows) {
  const mapElement = byId("trackingMap");
  const emptyState = byId("mapNoData");
  if (!window.L) {
    emptyState.textContent = "Map library could not load. Tracking records are still available above.";
    emptyState.classList.remove("d-none");
    return;
  }

  let points = [];
  sqlRows.forEach((row) => {
    if (row.accept_latitude != null && row.accept_longitude != null) {
      points.push({ type: "acceptance", time: row.accept_timestamp, lat: Number(row.accept_latitude), lng: Number(row.accept_longitude) });
    }
    if (row.delivery_latitude != null && row.delivery_longitude != null) {
      points.push({ type: "delivery", time: row.delivery_timestamp, lat: Number(row.delivery_latitude), lng: Number(row.delivery_longitude) });
    }
  });
  if (!points.length) {
    points = mongoRows
      .filter((event) => event.lat != null && event.lng != null)
      .map((event) => ({ type: event.event_type, time: event.timestamp, lat: Number(event.lat), lng: Number(event.lng) }));
  }
  points = points.filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));
  emptyState.classList.toggle("d-none", points.length > 0);
  if (!points.length) {
    trackingMarkers?.clearLayers();
    return;
  }

  if (!trackingMap) {
    trackingMap = L.map(mapElement, { scrollWheelZoom: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(trackingMap);
    trackingMarkers = L.layerGroup().addTo(trackingMap);
  }
  trackingMarkers.clearLayers();
  points.forEach((point) => {
    const isAcceptance = String(point.type).toLowerCase().includes("accept");
    const color = isAcceptance ? "#287b6c" : "#d66d52";
    L.circleMarker([point.lat, point.lng], {
      radius: 8,
      color,
      fillColor: color,
      fillOpacity: 0.9,
      weight: 2,
    }).bindPopup(`<strong>${escapeHtml(point.type)}</strong>${escapeHtml(formatTime(point.time))}<br>${point.lat}, ${point.lng}`).addTo(trackingMarkers);
  });
  const bounds = L.latLngBounds(points.map((point) => [point.lat, point.lng]));
  trackingMap.invalidateSize();
  if (points.length > 1) trackingMap.fitBounds(bounds.pad(0.25), { maxZoom: 15 });
  else trackingMap.setView(bounds.getCenter(), 13);
}

async function loadTracking(orderId) {
  clearAlert();
  byId("trackingOrderId").value = orderId;
  byId("trackingEmpty").classList.add("d-none");
  byId("trackingResults").classList.remove("d-none");
  byId("trackingResultId").textContent = orderId;
  byId("sqlTrackingBody").innerHTML = '<div class="detail-empty">Querying SQLite...</div>';
  byId("mongoTrackingBody").innerHTML = '<div class="detail-empty">Querying MongoDB...</div>';
  byId("sqlTime").textContent = "...";
  byId("mongoTime").textContent = "...";
  try {
    const comparison = await request(`/compare/tracking/${encodeURIComponent(orderId)}`);
    byId("sqlTime").textContent = Number(comparison.sql.execution_time_ms).toFixed(3);
    byId("mongoTime").textContent = Number(comparison.mongodb.execution_time_ms).toFixed(3);
    renderSqlTracking(comparison.sql.results || []);
    renderMongoTracking(comparison.mongodb.results || []);
    renderTrackingMap(comparison.sql.results || [], comparison.mongodb.results || []);
  } catch (error) {
    byId("trackingResults").classList.add("d-none");
    byId("trackingEmpty").classList.remove("d-none");
    showAlert(error.message);
  }
}

async function loadCourierOrders(courierId) {
  clearAlert();
  byId("courierOrdersTitle").textContent = `Courier ${courierId}`;
  byId("courierOrdersCount").textContent = "Loading...";
  try {
    const orders = await request(`/couriers/${encodeURIComponent(courierId)}/orders`);
    renderCourierOrders(courierId, orders);
  } catch (error) {
    byId("courierOrdersCount").textContent = "Unavailable";
    showAlert(error.message);
  }
}

async function loadDashboard() {
  clearAlert();
  const refreshButton = byId("refreshButton");
  refreshButton.disabled = true;
  refreshButton.classList.add("is-loading");
  setApiStatus("Syncing", "pending");
  try {
    const results = await Promise.allSettled([
      request("/orders"),
      request("/couriers"),
      request("/analytics/delivery-time"),
      request("/analytics/courier-performance?limit=8"),
      request("/analytics/delayed-orders"),
    ]);
    const [ordersResult, couriersResult, deliveryResult, performanceResult, delayedResult] = results;
    if (ordersResult.status === "fulfilled") {
      state.orders = ordersResult.value;
      byId("statOrders").textContent = state.orders.length.toLocaleString();
      renderOrders();
    }
    if (couriersResult.status === "fulfilled") {
      state.couriers = couriersResult.value;
      byId("statCouriers").textContent = state.couriers.length.toLocaleString();
      renderCouriers();
    }
    if (deliveryResult.status === "fulfilled") {
      byId("statDelivery").textContent = Number(deliveryResult.value.average_delivery_hours || 0).toFixed(2);
    }
    if (performanceResult.status === "fulfilled") renderCourierPerformance(performanceResult.value);
    if (delayedResult.status === "fulfilled") {
      const delayedOrders = delayedResult.value.orders || [];
      byId("statDelayed").textContent = delayedOrders.length.toLocaleString();
      renderDelayedOrders(delayedOrders);
    }
    const failed = results.find((result) => result.status === "rejected");
    if (failed) {
      showAlert(failed.reason.message || "Some dashboard data could not be loaded.");
    } else {
      setApiStatus("Connected", "ready");
    }
  } finally {
    refreshButton.disabled = false;
    refreshButton.classList.remove("is-loading");
  }
}

const orderModal = () => bootstrap.Modal.getOrCreateInstance(byId("orderModal"));
function openOrderModal(order = null) {
  const form = byId("orderForm");
  form.reset();
  byId("orderFormError").classList.add("d-none");
  state.editingOrderId = order ? String(order.order_id) : null;
  byId("orderModalTitle").textContent = order ? "Edit order" : "Create order";
  byId("saveOrderButton").textContent = order ? "Save changes" : "Save order";
  byId("formOrderId").disabled = Boolean(order);
  if (order) {
    byId("formOrderId").value = order.order_id ?? "";
    byId("formCourierId").value = order.courier_id ?? "";
    byId("formAoiId").value = order.aoi_id ?? "";
    byId("formClass").value = order.ds ?? "";
    byId("formIsDelayed").value = Number(order.is_delayed) === 1 ? "1" : "0";
    byId("formAcceptTime").value = order.accept_time ?? "";
    byId("formDeliveryTime").value = order.delivery_time ?? "";
  }
  orderModal().show();
}

async function saveOrder(event) {
  event.preventDefault();
  const formError = byId("orderFormError");
  formError.classList.add("d-none");
  const body = {
    order_id: byId("formOrderId").value.trim(),
    courier_id: byId("formCourierId").value.trim() || null,
    aoi_id: byId("formAoiId").value.trim() || null,
    ds: byId("formClass").value.trim() || null,
    is_delayed: Number(byId("formIsDelayed").value),
    accept_time: byId("formAcceptTime").value.trim() || null,
    delivery_time: byId("formDeliveryTime").value.trim() || null,
  };
  const editingId = state.editingOrderId;
  const path = editingId ? `/orders/${encodeURIComponent(editingId)}` : "/orders";
  const method = editingId ? "PUT" : "POST";
  try {
    await request(path, { method, body: JSON.stringify(body) });
    orderModal().hide();
    await loadDashboard();
  } catch (error) {
    formError.textContent = error.message;
    formError.classList.remove("d-none");
  }
}

async function handleOrderAction(action, orderId) {
  const order = state.orders.find((item) => String(item.order_id) === String(orderId));
  if (action === "track") {
    showView("tracking");
    await loadTracking(orderId);
  } else if (action === "edit" && order) {
    openOrderModal(order);
  } else if (action === "delete" && window.confirm(`Delete order ${orderId}?`)) {
    try {
      await request(`/orders/${encodeURIComponent(orderId)}`, { method: "DELETE" });
      await loadDashboard();
    } catch (error) {
      showAlert(error.message);
    }
  }
}

document.querySelectorAll("[data-view-target]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.viewTarget));
});
byId("refreshButton").addEventListener("click", loadDashboard);
byId("orderSearch").addEventListener("input", () => { state.orderPage = 1; renderOrders(); });
byId("previousPage").addEventListener("click", () => { state.orderPage -= 1; renderOrders(); });
byId("nextPage").addEventListener("click", () => { state.orderPage += 1; renderOrders(); });
byId("newOrderButton").addEventListener("click", () => openOrderModal());
byId("orderForm").addEventListener("submit", saveOrder);
byId("trackingForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const orderId = byId("trackingOrderId").value.trim();
  if (orderId) loadTracking(orderId);
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const { action, id } = button.dataset;
  if (action === "courier-orders") await loadCourierOrders(id);
  else await handleOrderAction(action, id);
});

loadDashboard();
