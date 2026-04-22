/** @odoo-module **/

const PORTAL_CAROUSEL_SELECTOR = ".o_portal_internal_carousel";
const INDICATOR_SELECTOR = ".carousel-indicators";
const ITEM_SELECTOR = ".carousel-item";
const CONTROL_SELECTOR = ".carousel-control-prev, .carousel-control-next";

function ensureCarouselId(carouselElement, index) {
    if (!carouselElement.id) {
        carouselElement.id = `portalInternalCarousel${index + 1}`;
    }
    return carouselElement.id;
}

function getActiveIndex(items) {
    const activeIndex = items.findIndex((item) => item.classList.contains("active"));
    return activeIndex >= 0 ? activeIndex : 0;
}

function syncActiveItem(items, activeIndex) {
    items.forEach((item, index) => {
        item.classList.toggle("active", index === activeIndex);
    });
}

function syncIndicators(carouselElement, carouselId, items, activeIndex) {
    const indicatorsElement = carouselElement.querySelector(INDICATOR_SELECTOR);
    if (!indicatorsElement) {
        return 0;
    }
    indicatorsElement.replaceChildren();
    items.forEach((item, index) => {
        const indicatorElement = document.createElement("button");
        indicatorElement.type = "button";
        indicatorElement.setAttribute("data-bs-target", `#${carouselId}`);
        indicatorElement.setAttribute("data-bs-slide-to", String(index));
        indicatorElement.setAttribute("aria-label", `Slide ${index + 1}`);
        if (index === activeIndex) {
            indicatorElement.classList.add("active");
            indicatorElement.setAttribute("aria-current", "true");
        }
        indicatorsElement.appendChild(indicatorElement);
    });
    return items.length;
}

function toggleCarouselControls(carouselElement, shouldShowControls) {
    for (const controlElement of carouselElement.querySelectorAll(CONTROL_SELECTOR)) {
        controlElement.classList.toggle("d-none", !shouldShowControls);
        controlElement.disabled = !shouldShowControls;
    }
}

function setupPortalInternalCarousel(carouselElement, index) {
    const Carousel = window.bootstrap && window.bootstrap.Carousel;
    if (!Carousel) {
        return;
    }

    const items = [...carouselElement.querySelectorAll(ITEM_SELECTOR)];
    if (!items.length) {
        toggleCarouselControls(carouselElement, false);
        return;
    }

    const carouselId = ensureCarouselId(carouselElement, index);
    const activeIndex = getActiveIndex(items);
    syncActiveItem(items, activeIndex);
    const indicatorCount = syncIndicators(carouselElement, carouselId, items, activeIndex);
    const canCycle = items.length > 1 && indicatorCount === items.length;

    toggleCarouselControls(carouselElement, canCycle);
    const carouselInstance = Carousel.getOrCreateInstance(carouselElement, {
        interval: canCycle ? 9000 : false,
        ride: false,
        touch: canCycle,
        wrap: canCycle,
    });
    if (canCycle) {
        carouselInstance.cycle();
    } else {
        carouselInstance.pause();
    }
}

function initPortalInternalCarousels() {
    const carouselElements = document.querySelectorAll(PORTAL_CAROUSEL_SELECTOR);
    carouselElements.forEach((carouselElement, index) => {
        setupPortalInternalCarousel(carouselElement, index);
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPortalInternalCarousels, { once: true });
} else {
    initPortalInternalCarousels();
}
