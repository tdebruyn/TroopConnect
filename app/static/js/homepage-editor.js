/* GrapesJS integration for the TroopConnect homepage editor.
 *
 * The page content area only is editable — the navbar and surrounding
 * layout are Django-rendered and outside the canvas. Uploaded images are
 * stored server-side (ImageAsset) and served from /media/.
 *
 * Uses GrapesJS 0.23.5 core only (no preset plugin — grapesjs-preset-webpage
 * 0.1.5 is incompatible with modern core, crashes in addComponents).
 */
(function () {
    "use strict";

    var container = document.getElementById("gjs");
    if (!container || typeof grapesjs === "undefined") {
        return;
    }

    var csrf = container.dataset.csrf;
    var saveUrl = container.dataset.saveUrl;
    var assetsUrl = container.dataset.assetsUrl;
    var page = container.dataset.page;
    var lang = container.dataset.lang;
    var i18n = JSON.parse(document.getElementById("editor-i18n").textContent);

    function parseJsonScript(id) {
        var node = document.getElementById(id);
        if (!node || !node.textContent.trim()) {
            return null;
        }
        try {
            return JSON.parse(node.textContent);
        } catch (err) {
            console.error("Invalid JSON in #" + id, err);
            return null;
        }
    }

    var projectData = parseJsonScript("project-json");
    var initialAssets = (parseJsonScript("assets-json") || []).map(function (asset) {
        return { src: asset.src, name: asset.name };
    });

    // Upload wiring for the asset manager: our own CSRF-protected endpoint.
    function uploadFiles(files) {
        var formData = new FormData();
        for (var i = 0; i < files.length; i++) {
            formData.append("file", files[i]);
        }
        fetch(assetsUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrf },
            body: formData,
            credentials: "same-origin",
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Upload failed: " + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                editor.AssetManager.add([{ src: data.src, name: data.name }]);
            })
            .catch(function (err) {
                console.error(err);
                window.alert(i18n.uploadFailed);
            });
    }

    /* Blocks (left panel) — a compact set covering text, images, colors,
     * fonts and sizing. Bootstrap classes are used directly since the canvas
     * loads the site's Bootstrap 5.
     */
    function troopconnectBlocks(editor) {
        var bm = editor.BlockManager;

        bm.add("section", {
            label: i18n.blockSection,
            category: i18n.catStructure,
            content: '<section class="py-4"><div class="container"></div></section>',
        });
        bm.add("columns-2", {
            label: i18n.blockColumns,
            category: i18n.catStructure,
            content:
                '<div class="container"><div class="row"><div class="col"></div><div class="col"></div></div></div>',
        });
        bm.add("columns-3", {
            label: i18n.blockColumns3,
            category: i18n.catStructure,
            content:
                '<div class="container"><div class="row"><div class="col"></div><div class="col"></div><div class="col"></div></div></div>',
        });
        bm.add("heading", {
            label: i18n.blockHeading,
            category: i18n.catBasic,
            content: "<h1>Heading</h1>",
        });
        bm.add("text", {
            label: i18n.blockText,
            category: i18n.catBasic,
            content: "<p>" + i18n.blockTextContent + "</p>",
        });
        bm.add("image", {
            label: i18n.blockImage,
            category: i18n.catBasic,
            content: { type: "image" },
        });
        bm.add("button", {
            label: i18n.blockButton,
            category: i18n.catBasic,
            content: '<a class="btn btn-primary" href="#">' + i18n.blockButtonContent + "</a>",
        });
        bm.add("divider", {
            label: i18n.blockDivider,
            category: i18n.catBasic,
            content: "<hr>",
        });
    }

    // Mirror the real front-end styles inside the canvas for fidelity, in the
    // same order base.html loads them: theme first, our overrides after, then
    // the canvas-only sheet.
    //
    // The Bootstrap path has to match base.html exactly. jsdelivr resolves the
    // path literally, so without the /dist/ segment it answers 404 ("Couldn't
    // find the requested file /css/bootstrap.min.css in bootstrap") and the
    // canvas silently gets no Bootstrap at all — no grid, no .card, and the
    // hero's white-on-white card text disappears.
    var canvasStyles = [
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.6/dist/css/bootstrap.min.css",
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.1/font/bootstrap-icons.min.css",
        "/static/fontawesomefree/css/all.min.css",
        "/static/vendor/template-unite/css/base.css",
        "/static/css/troopconnect.css",
        "/static/css/editor-canvas.css",
    ];

    var editor = grapesjs.init({
        container: "#gjs",
        plugins: [troopconnectBlocks],
        // Seed with the default/stored markup; a saved project replaces it
        // once the editor finished loading (see 'load' handler — calling
        // loadProjectData earlier races the canvas postLoad and crashes).
        components: container.innerHTML,
        storageManager: false,
        noticeOnUnload: false,
        telemetry: false,
        height: "100%",
        canvas: {
            scripts: [],
            styles: canvasStyles,
        },
        assetManager: {
            assets: initialAssets,
            uploadFile: uploadFiles,
        },
        styleManager: {
            sectors: [
                {
                    name: i18n.sectorDimension,
                    open: false,
                    buildProps: ["width", "min-height", "padding", "margin"],
                },
                {
                    name: i18n.sectorTypography,
                    open: false,
                    buildProps: [
                        "font-family",
                        "font-size",
                        "font-weight",
                        "color",
                        "text-align",
                        "line-height",
                    ],
                },
                {
                    name: i18n.sectorDecorations,
                    open: false,
                    buildProps: ["background-color", "border-radius", "border", "box-shadow"],
                },
                { name: i18n.sectorExtra, open: false, buildProps: ["opacity", "transition"] },
            ],
        },
    });

    /* --- The shape of the page ------------------------------------------
     *
     * The canvas is always: the hero, then the content area, and nothing else
     * at the top level.
     *
     * The hero comes from the page snippet and is not meant to be edited here
     * — its text is placeholder copy. It is locked, so it cannot be selected,
     * dragged, dropped into, copied or deleted.
     *
     * Everything else belongs in the content area below it. Pages saved before
     * that area existed — including the markup the old snippet shipped, which
     * wrapped the hero in a Bootstrap grid div — are repaired on load, so they
     * keep working and pick up the new structure the next time they are saved.
     */
    var HERO_SELECTOR = "header.masthead";
    var CONTENT_SELECTOR = ".tc-page-content";
    var CONTENT_MARKUP = '<main class="tc-page-content"></main>';

    function lock(component) {
        component.set({
            draggable: false,
            droppable: false,
            removable: false,
            copyable: false,
            selectable: false,
            hoverable: false,
            editable: false,
        });
        component.components().forEach(lock);
    }

    var normalizing = false;

    function normalizeCanvas() {
        if (normalizing) {
            return;
        }
        normalizing = true;
        try {
            var wrapper = editor.getWrapper();
            var hero = wrapper && wrapper.find(HERO_SELECTOR)[0];
            if (!hero) {
                // Nothing to anchor on: a page whose hero was replaced by hand
                // is left exactly as it is.
                return;
            }

            // Lift the hero out of the grid div the old snippet wrapped it in,
            // keeping whatever else lived there.
            var parent = hero.parent();
            if (parent && parent !== wrapper) {
                var strays = [];
                parent.components().forEach(function (component) {
                    if (component !== hero) {
                        strays.push(component);
                    }
                });
                hero.move(wrapper, { at: 0 });
                strays.forEach(function (component) {
                    component.move(wrapper);
                });
                if (!parent.components().length) {
                    parent.remove();
                }
            } else if (wrapper.components().indexOf(hero) !== 0) {
                hero.move(wrapper, { at: 0 });
            }

            var content = wrapper.find(CONTENT_SELECTOR)[0];
            if (!content) {
                content = wrapper.append(CONTENT_MARKUP)[0];
            }

            // Anything that is not the hero or the content area goes inside
            // the content area. That is what rescues blocks older versions of
            // this editor dropped at the top of the body, where they piled up
            // behind the hero instead of landing where they were dropped.
            wrapper.components().forEach(function (component) {
                if (component !== hero && component !== content) {
                    content.append(component);
                }
            });

            lock(hero);
        } catch (err) {
            // Loading a project rebuilds the canvas in the background, so a
            // pass can land on a half-built tree and throw. This runs again —
            // see the schedule below, and the 'update' hook after it — so a
            // failed pass is not worth reporting.
        } finally {
            normalizing = false;
        }
    }

    editor.on("load", function () {
        if (projectData) {
            editor.loadProjectData(projectData);
        }
        // GrapesJS 0.23 has no event that says "the loaded project is on
        // screen" (`canvas:frame:load` never fires, and a project load does
        // not emit `update`), so settle the canvas on a schedule instead. The
        // later passes matter on a slow connection, where the rebuilt frame
        // is still fetching its stylesheets. Each pass is a no-op once the
        // tree is already canonical.
        [0, 50, 250, 700, 1500].forEach(function (delay) {
            window.setTimeout(normalizeCanvas, delay);
        });
    });

    // Dropping a block anywhere but the content area (the strip above the hero,
    // the hero itself) is corrected as soon as the change lands.
    editor.on("update", normalizeCanvas);

    // Open the Blocks panel by default so the drag-and-drop library is
    // visible immediately (GrapesJS defaults to a hidden left panel).
    var openBlocks = editor.Panels.getButton("views", "open-blocks");
    if (openBlocks) {
        openBlocks.set("active", 1);
    }

    var saveButton = document.getElementById("btn-save");
    var toast = document.getElementById("save-toast");

    saveButton.addEventListener("click", function () {
        saveButton.disabled = true;
        fetch(saveUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrf,
            },
            credentials: "same-origin",
            body: JSON.stringify({
                page: page,
                lang: lang,
                project: editor.getProjectData(),
                html: editor.getHtml(),
                css: editor.getCss(),
            }),
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Save failed: " + response.status);
                }
                return response.json();
            })
            .then(function () {
                toast.style.display = "block";
                window.setTimeout(function () {
                    toast.style.display = "none";
                }, 2500);
            })
            .catch(function (err) {
                console.error(err);
                window.alert(i18n.saveFailed);
            })
            .finally(function () {
                saveButton.disabled = false;
            });
    });
})();
