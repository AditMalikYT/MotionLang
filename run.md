How to use it
# edit in the real-time Remotion editor
.venv/bin/motion examples/modern_demo.hmg --studio
cd studio && npm install && npm run dev      # http://localhost:5173

# export the edited timeline to MP4 through Remotion
cd studio && npm run render                  # -> studio/out/studio.mp4

# or render directly from the DSL (dependency-light Python engine)
.venv/bin/motion examples/modern_demo.hmg --render --output output/modern_demo.mp4
One note: examples/modern_demo.hmg currently sets mode = "render" so a bare motion examples/modern_demo.hmg renders instead of blocking on ffplay. --render also forces this regardless of config, so there's no way to accidentally hang a non-interactive build.



# For extention 

mkdir -p ~/.vscode/extensions/motion-language-support
cp -r ./* ~/.vscode/extensions/motion-language-support/