/* The enrolment desk's year chips.
 *
 * The answer swaps on its own, so the chips are never rebuilt: replacing them
 * would drop keyboard focus on every pick, and a full page load already
 * renders the selected state from the server. This mirrors that state onto
 * whichever chip was activated, so the control a parent touched acknowledges
 * the touch in the same moment the band below it changes.
 *
 * It reads across the whole desk, not just the chip's own card, because the
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
});
