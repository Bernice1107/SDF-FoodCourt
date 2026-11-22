const filters = ["locality", "cuisine", "preference"].map(id => document.getElementById(id));
const status = document.getElementById("status");
const list = document.getElementById("restaurants");
let requestNumber = 0;

function element(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function loadRestaurants() {
  const currentRequest = ++requestNumber;
  const params = new URLSearchParams();
  filters.forEach(filter => { if (filter.value) params.set(filter.id, filter.value); });
  list.replaceChildren();
  status.textContent = "Loading restaurants and menus…";
  try {
    const response = await fetch(`/api/restaurants?${params}`);
    if (!response.ok) throw new Error("Request failed");
    const restaurants = await response.json();
    if (currentRequest !== requestNumber) return;
    if (!restaurants.length) {
      status.textContent = "No restaurants match these filters. Try another selection.";
      return;
    }
    status.textContent = `${restaurants.length} restaurant${restaurants.length === 1 ? "" : "s"} found`;
    restaurants.forEach(restaurant => {
      const card = element("article", "", "card");
      card.append(element("p", restaurant.cuisine + " · " + restaurant.locality, "card-meta"));
      card.append(element("h3", restaurant.name));
      card.append(element("p", restaurant.rating === null ? "No ratings yet" : `${restaurant.rating} / 5 (${restaurant.review_count} reviews)`));
      restaurant.offers.forEach(offer => card.append(element("p", `Offer: ${offer}`, "card-meta")));
      const details = element("a", "View offers & reviews", "details-link");
      details.href = `/restaurants/${restaurant.id}`;
      card.append(details);
      const booking = element("a", "Book a table", "button book-button");
      booking.href = `/restaurants/${restaurant.id}/book`;
      card.append(booking);
      card.append(element("h4", "MENU"));
      const menu = element("ul", "", "menu");
      restaurant.menu.forEach(item => {
        const row = document.createElement("li");
        const description = document.createElement("div");
        description.append(element("span", item.name, "item-name"));
        description.append(element("span", item.preference, "preference"));
        const actions = document.createElement("div");
        actions.append(element("span", `₹${item.price} `, "price"));
        const form = document.createElement("form");
        form.method = "post";
        form.action = "/cart/add";
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "item_id";
        input.value = item.id;
        const button = element("button", "Add to cart");
        button.type = "submit";
        form.append(input, button);
        actions.append(form);
        row.append(description, actions);
        menu.append(row);
      });
      card.append(menu);
      list.append(card);
    });
  } catch (error) {
    if (currentRequest !== requestNumber) return;
    status.textContent = "Could not load restaurants. Check the server and refresh the page.";
  }
}
filters.forEach(filter => filter.addEventListener("change", loadRestaurants));
loadRestaurants();

