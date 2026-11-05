-- Renders plain ```mermaid fences (what GitHub renders) as diagrams in the portal.
-- Quarto only draws {mermaid} cells, so this emits the markup Quarto's own runtime expects and registers the
-- mermaid files bundled with the Quarto install as a dependency: they are copied to site_libs, no CDN.
local function runtime()
  local dir = pandoc.path.join({ os.getenv("QUARTO_SHARE_PATH") or "", "formats", "html", "mermaid" })
  -- An internal Quarto path: fail the render loudly if an upgrade moves it, rather than ship diagram source.
  local probe = io.open(pandoc.path.join({ dir, "mermaid.min.js" }), "r")
  if probe == nil then
    error("mermaid-fence: Quarto's bundled mermaid is not at " .. dir .. "; check the Quarto version (docs/portal.md)")
  end
  probe:close()
  quarto.doc.add_html_dependency({
    name = "quarto-diagram",
    version = "1.0.0",
    scripts = {
      { path = pandoc.path.join({ dir, "mermaid.min.js" }) },
      { path = pandoc.path.join({ dir, "mermaid-init.js" }) },
    },
    stylesheets = { pandoc.path.join({ dir, "mermaid.css" }) },
  })
end

local function escape(text)
  return (text:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"))
end

function CodeBlock(block)
  if not quarto.doc.is_format("html") or not block.classes:includes("mermaid") then
    return nil
  end
  runtime()
  -- Same nesting as a {mermaid} cell: mermaid-init.js reads options from ancestors of the <pre>.
  return pandoc.RawBlock(
    "html",
    '<div class="cell" data-layout-align="default"><div class="cell-output-display"><div>'
      .. '<figure class="figure"><div><pre class="mermaid mermaid-js">'
      .. escape(block.text)
      .. "</pre></div></figure></div></div></div>"
  )
end
