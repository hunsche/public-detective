// Global Animation Settings
gsap.registerPlugin(ScrollTrigger);

// Navbar Animation
gsap.from("nav", {
    y: -100,
    opacity: 0,
    duration: 1,
    ease: "power4.out",
    delay: 0.5
});

// Initial Page Load
document.addEventListener('DOMContentLoaded', () => {
    animatePageIn();
});

// HTMX Page Transitions
document.addEventListener('htmx:beforeSwap', (event) => {
    // Optional: Add exit animation here if needed, but HTMX swaps fast.
    // For smoother exits, we might need to pause the swap, animate, then resume.
    // For now, we'll rely on the enter animation of the new content.
});

document.addEventListener('htmx:afterSwap', (event) => {
    animatePageIn();
    reinitPageScripts();
});

function animatePageIn() {
    gsap.from("#main-content", {
        opacity: 0,
        y: 20,
        duration: 0.6,
        ease: "power2.out",
        clearProps: "all"
    });
}

function reinitPageScripts() {
    // Re-run specific page animations based on the URL or content
    if (document.querySelector('.hero-title')) {
        animateHero();
    }
    if (document.querySelector('.counter')) {
        animateCounters();
    }

    // Re-initialize ScrollTriggers
    ScrollTrigger.refresh();
}

// Hero Animation (Exported for re-use)
function animateHero() {
    gsap.to(".hero-title", {
        opacity: 1,
        y: 0,
        duration: 1,
        ease: "power3.out",
        delay: 0.2
    });
    gsap.to(".hero-subtitle", {
        opacity: 1,
        y: 0,
        duration: 1,
        ease: "power3.out",
        delay: 0.4
    });
    gsap.to(".hero-cta", {
        opacity: 1,
        y: 0,
        duration: 1,
        ease: "power3.out",
        delay: 0.6
    });

    gsap.from(".feature-card", {
        scrollTrigger: {
            trigger: ".feature-card",
            start: "top 80%",
        },
        y: 50,
        opacity: 0,
        duration: 0.8,
        stagger: 0.2,
        ease: "power3.out"
    });
}

// Dashboard Counters (Exported for re-use)
function animateCounters() {
    const counters = document.querySelectorAll('.counter');
    counters.forEach(counter => {
        const target = +counter.getAttribute('data-target');
        const duration = 2000; // ms
        const increment = target / (duration / 16);

        let current = 0;
        const updateCounter = () => {
            current += increment;
            if (current < target) {
                counter.innerText = Math.ceil(current);
                requestAnimationFrame(updateCounter);
            } else {
                counter.innerText = target;
            }
        };
        updateCounter();
    });

    gsap.from(".divide-y > div", {
        y: 20,
        opacity: 0,
        duration: 0.5,
        stagger: 0.1,
        ease: "power2.out",
        delay: 0.2
    });
}
