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
     * fonts, sizing: everything the superuser asked for. Bootstrap classes
     * are used directly since the canvas loads the site's Bootstrap 5.
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

    // Mirror the real front-end styles inside the canvas for fidelity.
    var canvasStyles = [
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.6/css/bootstrap.min.css",
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.1/font/bootstrap-icons.min.css",
        "/static/css/fede.css",
        "/static/fontawesomefree/css/all.min.css",
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

    if (projectData) {
        editor.on("load", function () {
            editor.loadProjectData(projectData);
        });
    }

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
