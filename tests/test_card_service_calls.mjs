// Regression test: the card must only request a service response from services
// that declare SupportsResponse.OPTIONAL. start/stop/add_favorite declare NONE,
// so sending return_response=true makes Home Assistant reject the call.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

let Card;
globalThis.HTMLElement = class {
  attachShadow() {
    this.shadowRoot = {};
    return this.shadowRoot;
  }
};
globalThis.customElements = {
  get: () => undefined,
  define: (_tag, ctor) => {
    Card = ctor;
  },
};
globalThis.window = {};

const source = readFileSync(
  new URL(
    "../custom_components/xiaomi_cooker_local/www/xiaomi-cooker-card.js",
    import.meta.url
  ),
  "utf8"
);
vm.runInThisContext(source);

const card = new Card();
card.render = () => {};
card.renderSuggestions = () => {};
card._cooker = { device_id: "dev-1" };
const calls = [];
card._hass = {
  callWS: async (request) => {
    calls.push(request);
    return { response: { recipes: [] } };
  },
};

await card.call("stop");
await card.call("start");
await card.call("add_favorite", { recipe: 1 });
await card.call("refresh_recipes");
await card.call("search_recipes", { query: "rice" }, true);
await card.call("get_recipe", { recipe: 1 }, true);

assert.equal(calls.length, 6);
for (const [index, service] of [
  "stop",
  "start",
  "add_favorite",
  "refresh_recipes",
].entries()) {
  assert.equal(
    "return_response" in calls[index],
    false,
    `${service} must not send return_response`
  );
}
for (const [index, service] of [
  [4, "search_recipes"],
  [5, "get_recipe"],
]) {
  assert.equal(calls[index].return_response, true, `${service} needs a response`);
}
for (const request of calls) {
  assert.equal(request.domain, "xiaomi_cooker_local");
  assert.deepEqual(request.target, { device_id: "dev-1" });
}

// Favorites: add/remove are actions (no response), listing needs a response.
card._detail = { id: 7, favorite: false, name_zh: "白米饭", name_en: "White rice" };
await card.toggleFavorite();
const addCall = calls.at(-1);
assert.equal(addCall.service, "add_favorite");
assert.deepEqual(addCall.service_data, { recipe: 7 });
assert.equal("return_response" in addCall, false);
assert.equal(card._detail.favorite, true);

await card.toggleFavorite();
const removeCall = calls.at(-1);
assert.equal(removeCall.service, "remove_favorite");
assert.equal("return_response" in removeCall, false);
assert.equal(card._detail.favorite, false);

await card.refreshFavorites();
const listCall = calls.at(-1);
assert.equal(listCall.service, "list_favorites");
assert.equal(listCall.return_response, true);

// Refresh is an action; progress comes from the shared HA sensor.
card._cooker.entities = { refreshing: "sensor.recipe_refresh_status" };
card._hass.states = {
  "sensor.recipe_refresh_status": {
    state: "download",
    attributes: { done: 5, total: 10 },
  },
};
assert.equal(card.state("refreshing"), "download");
assert.equal(card.attribute("refreshing", "done"), 5);
await card.refresh();
const refreshCall = calls.at(-1);
assert.equal(refreshCall.service, "refresh_recipes");
assert.equal("return_response" in refreshCall, false);
assert.equal(card._refresh, null);

// Selecting a suggestion opens just that recipe instead of leaving a result list.
card._hass.callWS = async (request) => {
  calls.push(request);
  if (request.service === "get_recipe") {
    return { response: { id: 9, name: "Selected recipe", name_zh: "选择的食谱", name_en: "Selected recipe" } };
  }
  return { response: { recipes: [] } };
};
card._results = [{ id: 1, name: "Other recipe" }];
await card.open("9");
assert.deepEqual(card._results, []);
assert.equal(card._query, "");
assert.equal(card._detail.name, "Selected recipe");
assert.equal(card.displayName({ name: "Selected recipe", name_zh: "选择的食谱" }), "Selected recipe (选择的食谱)");
assert.equal(calls.at(-1).service, "get_recipe");
assert.equal(calls.at(-1).return_response, true);

// Card exposes current action and recipe id sensors; no cook duration metric.
card._hass.states = {
  "sensor.rice_cooker_current_action": { state: "External Recipe" },
  "sensor.rice_cooker_active_recipe_id": { state: "unknown" },
};
const fallback = card.fallbackCooker();
assert.equal(fallback.entities.current_action, "sensor.rice_cooker_current_action");
assert.equal(fallback.entities.recipe_id, "sensor.rice_cooker_active_recipe_id");
assert.equal(fallback.entities.cook_duration, undefined);

console.log("card service payloads ok");
