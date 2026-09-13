#!/usr/bin/env bash
# Review the git worktrees of this repository: ask about every branch that is
# not on the base branch yet, merge the ones you approve, then offer to delete
# the worktrees whose work is safely on the base branch (or that you dropped).
#
# Usage:
#   scripts/worktree-tidy.sh               review, merge what you approve, clean up
#   scripts/worktree-tidy.sh --dry-run     print the report only, change nothing
#   scripts/worktree-tidy.sh --yes         merge every unmerged branch without asking
#   scripts/worktree-tidy.sh --push        push the base branch once merging is done
#
# Flags: -n/--dry-run, -y/--yes, -p/--push, -b/--base <branch>,
#        --force-locked, --force-dirty, -h/--help
#
# Environment overrides:
#   BASE_BRANCH   branch the work is merged into (default: main)
#
# Per-branch answers: [m]erge, [l]og (show the commits), [k]eep, [d]rop, [q]uit.
# Merges happen in the worktree that has the base branch checked out; nothing is
# ever force-pushed, and locked or dirty worktrees are never deleted silently.

set -euo pipefail

DRY_RUN=0
ASSUME_YES=0
PUSH=0
FORCE_LOCKED=0
FORCE_DIRTY=0
BASE_BRANCH="${BASE_BRANCH:-main}"

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
warn() { printf 'Warning: %s\n' "$*" >&2; }

usage() {
    sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run)    DRY_RUN=1 ;;
        -y|--yes)        ASSUME_YES=1 ;;
        -p|--push)       PUSH=1 ;;
        -b|--base)       shift; [ $# -gt 0 ] || die "--base needs a branch name"; BASE_BRANCH="$1" ;;
        --force-locked)  FORCE_LOCKED=1 ;;
        --force-dirty)   FORCE_DIRTY=1 ;;
        -h|--help)       usage 0 ;;
        *)               die "unknown option: $1 (try --help)" ;;
    esac
    shift
done

command -v git >/dev/null 2>&1 || die "git is not installed or not on PATH"
git rev-parse --git-dir >/dev/null 2>&1 || die "not inside a git repository"

# The main worktree is listed first by git; every git command runs through it so
# the script behaves the same whether it is started from a worktree or not.
MAIN_WT="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
[ -n "$MAIN_WT" ] || die "could not locate the main worktree"
MAIN_WT="$(cd "$MAIN_WT" && pwd -P)"

# ---------------------------------------------------------------------------
# Read the worktree list
# ---------------------------------------------------------------------------
WT_PATH=(); WT_NAME=(); WT_BRANCH=(); WT_LOCKED=(); WT_DETACHED=()

append_record() {
    WT_PATH+=("$1"); WT_NAME+=("$(basename "$1")"); WT_BRANCH+=("$2")
    WT_LOCKED+=("$3"); WT_DETACHED+=("$4")
}

# `git worktree list --porcelain` emits one blank-line-terminated record per
# worktree; fields we care about are `worktree`, `branch`, `locked`, `detached`.
load_worktrees() {
    local line=""
    local path="" branch="" locked=0 detached=0
    while IFS= read -r line || [ -n "$line" ]; do
        if [ -z "$line" ]; then
            if [ -n "$path" ]; then
                append_record "$path" "$branch" "$locked" "$detached"
            fi
            path=""; branch=""; locked=0; detached=0
            continue
        fi
        case "$line" in
            worktree\ *)          path="${line#worktree }" ;;
            branch\ refs/heads/*) branch="${line#branch refs/heads/}" ;;
            branch\ refs/*)       branch="" ;;   # another namespace (origin/…)
            detached)             detached=1 ;;
            locked|locked\ *)     locked=1 ;;
        esac
    done < <(git -C "$MAIN_WT" worktree list --porcelain)
    if [ -n "$path" ]; then
        append_record "$path" "$branch" "$locked" "$detached"
    fi
}

load_worktrees
[ "${#WT_PATH[@]}" -gt 0 ] || die "no worktrees found"

# The worktree the script is running in must never be deleted under the user.
SELF_WT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$SELF_WT" ]; then
    SELF_WT="$(cd "$SELF_WT" && pwd -P)"
fi

BASE_WT=""
for i in "${!WT_PATH[@]}"; do
    if [ "${WT_PATH[$i]}" = "$MAIN_WT" ]; then
        continue
    fi
    if [ "${WT_BRANCH[$i]}" = "$BASE_BRANCH" ]; then
        BASE_WT="${WT_PATH[$i]}"
    fi
done
# The base branch is usually checked out in the main worktree.
if [ -z "$BASE_WT" ] && [ "$(git -C "$MAIN_WT" symbolic-ref --quiet --short HEAD || true)" = "$BASE_BRANCH" ]; then
    BASE_WT="$MAIN_WT"
fi
[ -n "$BASE_WT" ] || die "base branch '$BASE_BRANCH' is not checked out in any worktree — check it out first"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# ask <prompt> <allowed-letters> — sets REPLY to one lowercase letter.
# Accepts a full word too ("merge" == "m"). Returns 1 on EOF, so callers stop
# asking instead of looping forever on a closed stdin.
ask() {
    local prompt="$1" allowed="$2" reply=""
    while :; do
        printf '%s' "$prompt"
        if ! read -r reply; then
            printf '\n'
            REPLY=""
            return 1
        fi
        reply="$(printf '%s' "$reply" | tr '[:upper:]' '[:lower:]')"
        reply="${reply:0:1}"
        if [ -n "$reply" ]; then
            case "$allowed" in
                *"$reply"*) REPLY="$reply"; return 0 ;;
            esac
        fi
        say "  Please answer one of [${allowed}]."
    done
}

is_merged() { git -C "$MAIN_WT" merge-base --is-ancestor "$1" "$BASE_BRANCH" 2>/dev/null; }

modified_count() { git -C "$1" status --porcelain --untracked-files=no 2>/dev/null | grep -c . || true; }
uncommitted_count() { git -C "$1" status --porcelain 2>/dev/null | grep -c . || true; }

# A merge needs the base worktree to be clean, but untracked files (the local
# workspace/ scratch dir, .claude/) are normal there and must not block it.
base_is_clean() { [ "$(modified_count "$BASE_WT")" -eq 0 ]; }

# Show a few uncommitted entries so a "dirty" verdict can be judged: leftover
# container files and scratch dirs look very different from real work.
dirty_preview() {
    local path="$1" total
    total="$(uncommitted_count "$path")"
    if [ "$total" -eq 0 ]; then
        return 0
    fi
    git -C "$path" status --porcelain 2>/dev/null | head -n 3 | sed 's/^/      /'
    if [ "$total" -gt 3 ]; then
        say "      … $((total - 3)) more"
    fi
    return 0
}

ahead_behind() {  # $1 = branch -> "AHEAD BEHIND" (how far the branch is from base)
    local behind=0 ahead=0
    read -r behind ahead < <(git -C "$MAIN_WT" rev-list --count --left-right "${BASE_BRANCH}...${1}" 2>/dev/null) || true
    printf '%s %s\n' "$ahead" "$behind"
}

show_commits() {
    local branch="$1" total
    total="$(git -C "$MAIN_WT" rev-list --count "${BASE_BRANCH}..${branch}" 2>/dev/null || echo 0)"
    say ""
    say "  ${total} commit(s) on ${branch} not on ${BASE_BRANCH}:"
    git -C "$MAIN_WT" log --oneline --no-decorate -n 20 "${BASE_BRANCH}..${branch}" | sed 's/^/    /'
    [ "$total" -gt 20 ] && say "    … $((total - 20)) more"
    say ""
    git -C "$MAIN_WT" diff --stat "${BASE_BRANCH}...${branch}" | tail -n 1 | sed 's/^/    /'
    say ""
}

merge_branch() {  # $1 = branch — merges into the base worktree, never force
    local branch="$1" out=""
    if [ "$DRY_RUN" -eq 1 ]; then
        say "  (dry run) would merge ${branch} into ${BASE_BRANCH}"
        return 0
    fi
    if out="$(git -C "$BASE_WT" merge --ff-only --no-edit "$branch" 2>&1)"; then
        say "  Merged ${branch} into ${BASE_BRANCH} (fast-forward)."
        return 0
    fi
    if out="$(git -C "$BASE_WT" merge --no-edit "$branch" 2>&1)"; then
        say "  Merged ${branch} into ${BASE_BRANCH} (merge commit)."
        return 0
    fi
    # A conflicted merge leaves the base worktree mid-merge: undo it.
    if [ -f "$(git -C "$BASE_WT" rev-parse --git-path MERGE_HEAD)" ]; then
        git -C "$BASE_WT" merge --abort >/dev/null 2>&1 || true
    fi
    say "  Could not merge ${branch} — left untouched:"
    printf '%s\n' "$out" | sed 's/^/    /'
    return 1
}

# The dev container runs as root and owns app/.ruff_cache and app/media, which
# makes the whole worktree undeletable as a normal user.
clean_root_owned() {
    local path="$1"
    command -v docker >/dev/null 2>&1 || return 1
    docker image inspect troopconnect-dev:latest >/dev/null 2>&1 || return 1
    say "  Clearing root-owned files with the troopconnect-dev image…"
    docker run --rm -v "${path}:/wt" troopconnect-dev:latest \
        sh -c 'rm -rf /wt/app/.ruff_cache /wt/app/media' || return 1
}

# A merged branch is redundant once its worktree is gone; a dropped one is kept
# (it still holds the only copy of that work).
delete_branch_if_merged() {
    local i="$1" branch="${WT_BRANCH[$i]}"
    if [ -z "$branch" ] || [ "${WT_RESOLVED[$i]}" != "merged" ]; then
        return 0
    fi
    if git -C "$MAIN_WT" branch -d "$branch" >/dev/null 2>&1; then
        say "  Deleted merged branch ${branch} (remote copy left alone)"
    else
        say "  Kept branch ${branch} (git would not delete it safely)"
    fi
    return 0
}

manual_cleanup_hint() {
    local path="$1"
    say "  Left in place. To clean it up manually:"
    say "    docker run --rm -v \"${path}:/wt\" troopconnect-dev:latest \\"
    say "      sh -c 'rm -rf /wt/app/.ruff_cache /wt/app/media'"
    say "    rm -rf \"${path}\" && git -C \"${MAIN_WT}\" worktree prune"
}

remove_worktree() {  # $1 = index — returns 0 only when the worktree is gone
    local i="$1" path="${WT_PATH[$i]}"
    local dirty="${WT_DIRTY[$i]}" locked="${WT_LOCKED[$i]}" out="" args=(worktree remove)
    if [ "$dirty" -gt 0 ]; then
        args+=(--force)
    fi
    # git refuses to drop a locked worktree without -f -f.
    if [ "$locked" -eq 1 ]; then
        args+=(--force --force)
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        say "  (dry run) would delete ${path}"
        return 0
    fi

    if out="$(git -C "$MAIN_WT" "${args[@]}" "$path" 2>&1)"; then
        say "  Deleted ${path}"
        delete_branch_if_merged "$i"
        return 0
    fi

    printf '%s\n' "$out" | sed 's/^/    /'
    case "$out" in
        *[Pp]ermission*|*"Operation not permitted"*)
            # git deregisters the worktree before it walks the files, so a
            # blocked removal usually still leaves the directory on disk — the
            # only way through is to clear the root-owned files, then rm.
            say "  ${WT_NAME[$i]} could not be fully removed: root-owned files left by the dev container."
            if ! ask "  Clear them with the troopconnect-dev image and retry? [y/N] " "yn" \
               || [ "$REPLY" != "y" ]; then
                manual_cleanup_hint "$path"
                return 1
            fi
            if ! clean_root_owned "$path"; then
                say "  The dev container could not clear them (is docker running, is the image built?)."
                manual_cleanup_hint "$path"
                return 1
            fi
            rm -rf "$path" 2>/dev/null || true
            git -C "$MAIN_WT" worktree prune >/dev/null 2>&1 || true
            if [ -d "$path" ]; then
                say "  Still not empty:"
                ls -A "$path" 2>/dev/null | sed 's/^/    /'
                return 1
            fi
            say "  Deleted ${path} (after clearing the root-owned files)"
            delete_branch_if_merged "$i"
            return 0
            ;;
        *)
            say "  Could not delete ${path} — left in place."
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
say "Worktrees of ${MAIN_WT}"
say "Base branch: ${BASE_BRANCH} (checked out in ${BASE_WT})"
say ""

WT_STATE=(); WT_DIRTY=(); WT_AHEAD=()
CAND=()
n=0
for i in "${!WT_PATH[@]}"; do
    path="${WT_PATH[$i]}"
    branch="${WT_BRANCH[$i]}"
    dirty="$(uncommitted_count "$path")"
    ahead=0
    if [ -n "$branch" ]; then
        read -r ahead _behind < <(ahead_behind "$branch") || true
    fi
    if [ "${WT_DETACHED[$i]}" -eq 1 ] || [ -z "$branch" ]; then
        state="detached"
    elif [ "$path" = "$BASE_WT" ]; then
        state="base"
    elif is_merged "$branch"; then
        state="merged"
    else
        state="unmerged"
    fi

    if [ "$path" = "$BASE_WT" ]; then
        desc="base checkout — skipped"
    elif [ "$path" = "$SELF_WT" ]; then
        desc="the worktree this script runs in — skipped"
    else
        case "$state" in
            merged)   desc="already on ${BASE_BRANCH}" ;;
            unmerged) desc="${ahead} commit(s) ahead of ${BASE_BRANCH}" ;;
            detached) desc="detached HEAD — nothing to merge" ;;
            *)        desc="$state" ;;
        esac
        [ "${WT_LOCKED[$i]}" -eq 1 ] && desc="${desc} · locked"
        [ "$dirty" -gt 0 ] && desc="${desc} · ${dirty} uncommitted change(s)"
    fi

    n=$((n + 1))
    printf '  %2d. %-38s %s\n' "$n" "${WT_NAME[$i]}" "$desc"
    WT_STATE+=("$state"); WT_DIRTY+=("$dirty"); WT_AHEAD+=("$ahead")
    if [ "$path" != "$BASE_WT" ] && [ "$path" != "$SELF_WT" ]; then
        CAND+=("$i")
    fi
done
say ""

if [ "$DRY_RUN" -eq 1 ]; then
    settled=0
    for i in "${CAND[@]}"; do
        if [ "${WT_STATE[$i]}" = "merged" ]; then
            settled=$((settled + 1))
            if [ "$settled" -eq 1 ]; then
                say "Settled worktrees (already on ${BASE_BRANCH}, offered for deletion):"
            fi
            say "    ${WT_NAME[$i]}"
        fi
    done
    if [ "$settled" -eq 0 ]; then
        say "No worktree is ready for deletion."
    fi
    say ""
    say "Dry run — nothing was merged or deleted."
    exit 0
fi

# ---------------------------------------------------------------------------
# Resolve the unmerged branches
# ---------------------------------------------------------------------------
# Branches already on the base branch are settled no matter what the review
# decides, so they stay eligible for cleanup even if the review is cut short.
WT_RESOLVED=()
for i in "${!WT_PATH[@]}"; do
    if [ "${WT_STATE[$i]}" = "merged" ]; then
        WT_RESOLVED+=("merged")
    else
        WT_RESOLVED+=("")
    fi
done

MERGE_BLOCKED=0
if ! base_is_clean; then
    warn "${BASE_WT} has uncommitted changes to tracked files — merging is skipped"
    MERGE_BLOCKED=1
fi

STOP=0
for i in "${CAND[@]}"; do
    n=$((i + 1))
    state="${WT_STATE[$i]}"
    branch="${WT_BRANCH[$i]}"
    if [ "$state" = "merged" ]; then
        WT_RESOLVED[$i]="merged"
        continue
    fi
    if [ "$state" != "unmerged" ]; then
        say "${n}. ${WT_NAME[$i]} — nothing to merge (${state}), left alone."
        continue
    fi

    if [ "$MERGE_BLOCKED" -eq 1 ]; then
        say "${n}. ${branch} — skipping the merge (base worktree is dirty)."
        continue
    fi

    if [ "${WT_DIRTY[$i]}" -gt 0 ]; then
        say ""
        warn "${WT_DIRTY[$i]} uncommitted change(s) in this worktree are not on any commit yet;"
        warn "merging ${branch} would not include them."
    fi

    say "${n}. ${WT_NAME[$i]} — ${branch}, ${WT_AHEAD[$i]} commit(s) ahead of ${BASE_BRANCH}"
    while :; do
        if [ "$ASSUME_YES" -eq 1 ]; then
            REPLY="m"
        elif ! ask "  [m]erge  [l]og  [k]eep  [d]rop  [q]uit > " "mlkdq"; then
            STOP=1
        fi
        case "${REPLY:-q}" in
            m)
                if merge_branch "$branch"; then
                    WT_RESOLVED[$i]="merged"
                else
                    WT_RESOLVED[$i]="kept"
                fi
                break ;;
            l) show_commits "$branch" ;;
            k)
                say "  Kept ${branch} and its worktree."
                WT_RESOLVED[$i]="kept"
                break ;;
            d)
                say "  Dropped: ${branch} is left unmerged; its worktree can be deleted."
                WT_RESOLVED[$i]="dropped"
                break ;;
            q|*)
                say "  Stopping the review — the remaining unmerged branches are left alone."
                STOP=1
                break ;;
        esac
    done
    if [ "$STOP" -eq 1 ]; then
        break
    fi
done

if [ "$MERGE_BLOCKED" -eq 0 ] && ! base_is_clean; then
    warn "${BASE_WT} now has uncommitted changes — investigate before continuing"
fi

# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------
PUSHED=0
upstream="$(git -C "$BASE_WT" rev-parse --abbrev-ref --symbolic-full-name "${BASE_BRANCH}@{upstream}" 2>/dev/null || true)"
if [ -n "$upstream" ]; then
    pending="$(git -C "$BASE_WT" rev-list --count "${upstream}..${BASE_BRANCH}")"
else
    pending=0
fi
if [ "$pending" -gt 0 ]; then
    remote="${upstream%%/*}"
    say ""
    say "${BASE_BRANCH} is ${pending} commit(s) ahead of ${upstream}."
    if [ "$PUSH" -eq 1 ]; then
        REPLY="y"
    else
        ask "Push ${BASE_BRANCH} to ${remote}? [y/N] " "yn" || REPLY="n"
    fi
    if [ "${REPLY:-n}" = "y" ]; then
        if git -C "$BASE_WT" push "$remote" "$BASE_BRANCH"; then
            PUSHED=1
        else
            warn "push failed — ${BASE_BRANCH} still needs pushing manually"
        fi
    else
        say "Not pushed. When you are ready: git -C ${BASE_WT} push ${remote} ${BASE_BRANCH}"
    fi
fi

# ---------------------------------------------------------------------------
# Delete the finished worktrees
# ---------------------------------------------------------------------------
DELETE=()
BLOCKED=()
for i in "${CAND[@]}"; do
    case "${WT_RESOLVED[$i]}" in
        merged|dropped)
            if [ "${WT_LOCKED[$i]}" -eq 1 ] && [ "$FORCE_LOCKED" -eq 0 ]; then
                BLOCKED+=("$i")
            elif [ "${WT_DIRTY[$i]}" -gt 0 ] && [ "$FORCE_DIRTY" -eq 0 ]; then
                BLOCKED+=("$i")
            else
                DELETE+=("$i")
            fi
            ;;
    esac
done

if [ "${#BLOCKED[@]}" -gt 0 ]; then
    say ""
    warn "Not offered for deletion (locked or has uncommitted changes):"
    for i in "${BLOCKED[@]}"; do
        why="locked (possibly in use by another session)"
        if [ "${WT_DIRTY[$i]}" -gt 0 ]; then
            why="uncommitted changes"
        fi
        say "    ${WT_NAME[$i]} — ${why}"
        dirty_preview "${WT_PATH[$i]}"
    done
    say "    Re-run with --force-locked / --force-dirty if you really mean to delete them."
fi

if [ "${#DELETE[@]}" -eq 0 ]; then
    say ""
    say "Nothing left to delete."
else
    say ""
    say "Worktrees whose work is settled (branch merged, or dropped on purpose):"
    for i in "${DELETE[@]}"; do
        branch="${WT_BRANCH[$i]}"
        [ -z "$branch" ] && branch="detached HEAD"
        printf '    %-38s %s\n' "${WT_NAME[$i]}" "${branch} [${WT_RESOLVED[$i]}]"
    done
    for i in "${DELETE[@]}"; do
        if [ "${WT_DIRTY[$i]}" -gt 0 ]; then
            warn "${WT_NAME[$i]}: these uncommitted changes go away with the worktree"
            dirty_preview "${WT_PATH[$i]}"
        fi
    done

    say ""
    if ask "Delete these ${#DELETE[@]} worktree(s)? [y]es  [p]ick one by one  [N]o > " "ypn"; then
        case "$REPLY" in
            y)
                for i in "${DELETE[@]}"; do remove_worktree "$i" || true; done ;;
            p)
                for i in "${DELETE[@]}"; do
                    branch="${WT_BRANCH[$i]}"
                    if ask "${WT_NAME[$i]} [${branch:-detached}] — delete? [y/N] " "yn" \
                       && [ "$REPLY" = "y" ]; then
                        remove_worktree "$i" || true
                    else
                        say "  Kept ${WT_NAME[$i]}"
                    fi
                done ;;
            *)
                say "Kept every worktree." ;;
        esac
    else
        say "Kept every worktree."
    fi
    git -C "$MAIN_WT" worktree prune >/dev/null 2>&1 || true
fi

say ""
say "Done."
git -C "$MAIN_WT" worktree list
if [ "$PUSHED" -eq 1 ]; then
    say "Pushed ${BASE_BRANCH} to ${remote}."
fi
