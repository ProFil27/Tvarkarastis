/*
 * Time input: type 930 -> 09:30, arrow keys change the time, a short list of suggestions appears on focus.
 * One set of delegated listeners serves every [data-time-input] on the page (also long review tables).
 */
(function () {
    "use strict";

    var SUGGEST_FROM = 7 * 60, SUGGEST_TO = 21 * 60, SUGGEST_STEP = 15, DEFAULT_MINUTES = 8 * 60;

    function pad(n) { return (n < 10 ? "0" : "") + n; }
    function format(minutes) { return pad(Math.floor(minutes / 60)) + ":" + pad(minutes % 60); }

    // "HH:MM" -> minutes since midnight, or null if it is not a valid 24 h time.
    function toMinutes(text) {
        var m = /^([01]?[0-9]|2[0-3]):([0-5][0-9])$/.exec(text || "");
        return m ? Number(m[1]) * 60 + Number(m[2]) : null;
    }

    // Digits typed so far -> text shown while typing (without forcing a colon while deleting).
    function liveFormat(raw, deleting) {
        var digits = raw.replace(/\D/g, "").slice(0, 4);
        if (digits.length >= 3) { return digits.slice(0, 2) + ":" + digits.slice(2); }
        if (digits.length === 2 && !deleting) { return digits + ":"; }
        return digits;
    }

    // Final value when the field loses focus: "9" -> 09:00, "930" -> 09:30, "14" -> 14:00; invalid stays as typed.
    function normalize(raw) {
        var digits = raw.replace(/\D/g, "");
        if (!digits) { return ""; }
        var hours, minutes;
        if (digits.length <= 2) { hours = Number(digits); minutes = 0; }
        else if (digits.length === 3) { hours = Number(digits.slice(0, 1)); minutes = Number(digits.slice(1)); }
        else { hours = Number(digits.slice(0, 2)); minutes = Number(digits.slice(2, 4)); }
        if (hours > 23 || minutes > 59) { return raw; }
        return pad(hours) + ":" + pad(minutes);
    }

    var api = { format: format, toMinutes: toMinutes, liveFormat: liveFormat, normalize: normalize };
    if (typeof module !== "undefined" && module.exports) { module.exports = api; }
    if (typeof document === "undefined") { return; }
    window.TimeField = api;

    var menu = null, owner = null;

    function markValidity(input) {
        var empty = input.value === "";
        var valid = empty || toMinutes(input.value) !== null;
        input.classList.toggle("invalid", !valid);
        if (valid) { input.removeAttribute("aria-invalid"); } else { input.setAttribute("aria-invalid", "true"); }
    }

    function closeMenu() {
        if (menu) { menu.remove(); menu = null; owner = null; }
    }

    // `filter` is true while the user types: then only times that start with the typed digits are offered.
    // On focus the whole list is shown and the time nearest to the current value is highlighted.
    function openMenu(input, filter) {
        closeMenu();
        var typed = filter ? input.value.replace(/\D/g, "") : "";
        var current = toMinutes(input.value);
        var items = [];
        for (var t = SUGGEST_FROM; t <= SUGGEST_TO; t += SUGGEST_STEP) {
            var label = format(t);
            if (!typed || label.replace(":", "").indexOf(typed) === 0) { items.push({ minutes: t, label: label }); }
        }
        if (!items.length) { return; }

        menu = document.createElement("div");
        menu.className = "time-menu";
        menu.setAttribute("role", "listbox");
        var nearest = null;
        items.forEach(function (item) {
            var option = document.createElement("div");
            option.className = "time-option";
            option.setAttribute("role", "option");
            option.textContent = item.label;
            option.dataset.value = item.label;
            if (current !== null && (nearest === null || Math.abs(item.minutes - current) < Math.abs(nearest.minutes - current))) {
                nearest = { minutes: item.minutes, node: option };
            }
            menu.appendChild(option);
        });
        var rect = input.getBoundingClientRect();
        menu.style.left = (rect.left + window.pageXOffset) + "px";
        menu.style.top = (rect.bottom + window.pageYOffset + 4) + "px";
        menu.style.minWidth = rect.width + "px";
        document.body.appendChild(menu);
        owner = input;
        if (nearest) { nearest.node.classList.add("near"); menu.scrollTop = nearest.node.offsetTop - 60; }
    }

    function step(input, minutes) {
        var base = toMinutes(normalize(input.value));
        var next = (base === null ? DEFAULT_MINUTES : base) + minutes;
        input.value = format(Math.min(Math.max(next, 0), 23 * 60 + 59));
        markValidity(input);
    }

    document.addEventListener("focusin", function (event) {
        if (event.target.matches("[data-time-input]")) { openMenu(event.target, false); }
    });

    document.addEventListener("input", function (event) {
        var input = event.target;
        if (!input.matches || !input.matches("[data-time-input]")) { return; }
        input.value = liveFormat(input.value, event.inputType === "deleteContentBackward");
        markValidity(input);
        openMenu(input, true);
    });

    document.addEventListener("keydown", function (event) {
        var input = event.target;
        if (!input.matches || !input.matches("[data-time-input]")) { return; }
        if (event.key === "ArrowUp" || event.key === "ArrowDown") {
            event.preventDefault();
            var size = event.shiftKey ? 60 : 5;
            step(input, event.key === "ArrowUp" ? size : -size);
            closeMenu();
        } else if (event.key === "Escape") {
            closeMenu();
        }
    });

    document.addEventListener("focusout", function (event) {
        var input = event.target;
        if (!input.matches || !input.matches("[data-time-input]")) { return; }
        input.value = normalize(input.value);
        markValidity(input);
        closeMenu();
    });

    // mousedown (not click) so the choice is applied before the input loses focus.
    document.addEventListener("mousedown", function (event) {
        if (event.target.classList && event.target.classList.contains("time-option") && owner) {
            event.preventDefault();
            owner.value = event.target.dataset.value;
            markValidity(owner);
            owner.dispatchEvent(new Event("change", { bubbles: true }));
            closeMenu();
        }
    });
})();
