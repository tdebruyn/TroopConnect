/* The enrolment desk's year chips.
 *
 * The answer swaps on its own, so the rail is never rebuilt: replacing it
 * would drop keyboard focus on every pick, and a full page load already
 * renders the selected state from the server. This mirrors that state onto
 * whichever chip was activated — and onto the branch segment holding it — so
 * the control a parent touched acknowledges the touch in the same moment the
 * band below it changes.
 *
 * It reads across the whole rail, not just the chip's own segment, because the
 * year a parent moves to is usually in a different branch from the one they
 * were looking at — and two selected years would misstate the answer.
 */
document.addEventListener("click", function (event) {
  var chip = event.target.closest && event.target.closest(".desk-year");
  if (!chip) {
    return;
  }
  var chips = document.querySelectorAll(".desk-years .desk-year");
  for (var i = 0; i < chips.length; i++) {
    var picked = chips[i] === chip;
    chips[i].classList.toggle("desk-year-on", picked);
    if (picked) {
      chips[i].setAttribute("aria-current", "true");
    } else {
      chips[i].removeAttribute("aria-current");
    }
  }
  var segments = document.querySelectorAll(".desk-segment");
  var chosen = chip.closest(".desk-segment");
  for (var j = 0; j < segments.length; j++) {
    segments[j].classList.toggle("desk-segment-on", segments[j] === chosen);
  }
});

/* A phone stacks the four rooms, so the answer lands a screen or two below the
 * chip that was just touched. Bring it into view after the swap unless it is
 * already there; the chip keeps focus either way, so a keyboard reader is not
 * moved away from the control they used. */
document.body.addEventListener("htmx:afterSwap", function (event) {
  var answer = event.detail.target;
  if (!answer || answer.id !== "desk-answer") {
    return;
  }
  if (answer.getBoundingClientRect().bottom <= window.innerHeight - 16) {
    return;
  }
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  answer.scrollIntoView({
    block: "nearest",
    behavior: reduce ? "auto" : "smooth",
  });
});
