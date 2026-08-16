/* GrapesJS integration for the TroopConnect homepage editor.
 *
 * The page content area only is editable — the navbar and surrounding
 * layout are Django-rendered and outside the canvas. Uploaded images are
 * stored server-side (ImageAsset) and served from /media/.
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

    // Mirror the real front-end styles inside the canvas for fidelity.
    var canvasStyles = [
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.6/css/bootstrap.min.css",
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.1/font/bootstrap-icons.min.css",
        "/static/css/fede.css",
        "/static/fontawesomefree/css/all.min.css",
    ];

    var editor = grapesjs.init({
        container: "#gjs",
        plugins: ["gjs-preset-webpage"],
        storageManager: false,
        noticeOnUnload: false,
        height: "100%",
        canvas: {
            scripts: [],
            styles: canvasStyles,
        },
        assetManager: {
            assets: initialAssets,
            uploadFile: uploadFiles,
        },
    });

    if (projectData) {
        editor.setProjectData(projectData);
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
                editor.setDirty(false);
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
