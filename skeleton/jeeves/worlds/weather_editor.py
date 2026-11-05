"""Offline weather/visibility authoring with CSP-hashed, unapproved export."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .weather import validate_weather
from .world_canon import CanonError, canonical

JS = r"""
"use strict";
const payload = JSON.parse(document.getElementById("source-data").textContent);
const source = payload.source;
const choices = payload.choices;
const root = document.getElementById("editor");
const fields = [];
const overrideFields = [];
const weatherOptions = ["clear", "fog", "rain", "snow", "storm", "wind"];
const visibilityOptions = ["clear", "limited", "obscured"];
function node(tag, text) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  return e;
}
function selector(options, value) {
  const e = node("select");
  for (const item of options) {
    const opt = node("option", item);
    opt.value = item; e.append(opt);
  }
  e.value = value;
  return e;
}
function labeled(label, field, parent) {
  const e = node("label", label);
  e.append(field); parent.append(e);
  return field;
}
root.append(node("h1", "Original world weather editor"));
root.append(node("p", "Local draft editing only; no approval or publication."));
for (const scene of source.scenes) {
  const section = node("section");
  section.append(node("h2", "Scene: " + scene.scene));
  const weather = labeled("Weather", selector(weatherOptions, scene.weather), section);
  const visibility = labeled("Visibility", selector(visibilityOptions, scene.visibility), section);
  const description = node("textarea");
  description.value = scene.description; description.maxLength = 1024;
  description.rows = 3; description.cols = 72;
  labeled("Original atmosphere prose", description, section);
  fields.push({weather, visibility, description});
  root.append(section);
}
const overrideArea = node("section");
overrideArea.append(node("h2", "Choice weather overrides"));
root.append(overrideArea);
function addOverride(item) {
  const row = node("div");
  const choice = labeled("Choice", selector(choices, item.choice), row);
  const weather = labeled("Weather", selector(weatherOptions, item.weather), row);
  const visibility = labeled("Visibility", selector(visibilityOptions, item.visibility), row);
  const remove = node("button", "Remove override");
  remove.type = "button";
  const field = {choice, weather, visibility, row};
  overrideFields.push(field);
  remove.addEventListener("click", () => {
    const index = overrideFields.indexOf(field);
    if (index >= 0) overrideFields.splice(index, 1);
    row.remove();
  });
  row.append(remove);
  overrideArea.append(row);
}
for (const item of source.overrides) addOverride(item);
const add = node("button", "Add choice override");
add.type = "button"; add.disabled = choices.length === 0;
add.addEventListener("click", () => {
  if (overrideFields.length >= choices.length) {
    status.textContent = "Every authored choice already has an override.";
    return;
  }
  const used = new Set(overrideFields.map(field => field.choice.value));
  const available = choices.find(choice => !used.has(choice));
  if (available !== undefined) {
    addOverride({choice:available, weather:"clear", visibility:"clear"});
  }
});
root.append(add);
const exportButton = node("button", "Export unapproved weather source");
exportButton.type = "button"; root.append(exportButton);
const status = node("p");
status.setAttribute("role", "status");
status.setAttribute("aria-live", "polite");
root.append(status);
exportButton.addEventListener("click", () => {
  const draft = JSON.parse(JSON.stringify(source));
  draft.approved = false; draft.review_note = "";
  for (let i = 0; i < fields.length; i++) {
    draft.scenes[i].weather = fields[i].weather.value;
    draft.scenes[i].visibility = fields[i].visibility.value;
    draft.scenes[i].description = fields[i].description.value;
  }
  draft.overrides = overrideFields.map(field => ({
    choice:field.choice.value, weather:field.weather.value,
    visibility:field.visibility.value,
  })).sort((a,b) => a.choice < b.choice ? -1 : a.choice > b.choice ? 1 : 0);
  if (new Set(draft.overrides.map(row => row.choice)).size !== draft.overrides.length) {
    status.textContent = "Duplicate choice override; resolve before export.";
    return;
  }
  const body = JSON.stringify(draft, null, 2) + "\n";
  if (new TextEncoder().encode(body).length > 524288) {
    status.textContent = "Source exceeds bounded import size."; return;
  }
  const url = URL.createObjectURL(new Blob([body], {type:"application/json"}));
  const link = node("a");
  link.href = url; link.download = source.world_id + ".weather.unapproved.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  status.textContent = "Exported unapproved source for reviewed CLI publication.";
});
""".strip()


def render_weather_editor(source: Any, world: Any) -> bytes:
    validate_weather(source, world)
    if source["approved"]:
        raise CanonError("weather_editor_requires_draft")
    payload = canonical({
        "source": source,
        "choices": sorted(choice["id"] for choice in world["choices"]),
    }).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(JS.encode()).digest()).decode("ascii")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + policy +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        '<title>' + html.escape(world["id"], quote=True) +
        ' — weather editor</title></head><body><main id="editor"></main>'
        '<script id="source-data" type="application/json">' + payload +
        '</script><script>' + JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("weather_editor_too_large")
    return page
