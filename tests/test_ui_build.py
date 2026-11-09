import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class UiBuildContract(unittest.TestCase):
    def test_production_uses_the_shared_immutable_bootstrap(self):
        build = (ROOT / 'build-images.sh').read_text()
        self.assertIn('./build-ui.sh', build)
        self.assertNotIn('corepack enable', build)
        bootstrap = (ROOT / 'ui/build-ui.sh').read_text()
        self.assertIn('yarn install --immutable', bootstrap)
        self.assertIn('yarn lint', bootstrap)
        self.assertIn('yarn build', bootstrap)

    def test_developer_image_has_exact_interactive_yarn_before_mount(self):
        package = json.loads((ROOT / 'ui/package.json').read_text())
        pin = package['packageManager'].removeprefix('yarn@')
        recipe = (ROOT / 'ui/Containerfile').read_text()
        self.assertIn('@yarnpkg/cli-dist@' + pin, recipe)
        self.assertNotIn('corepack enable', recipe)
        prod_node = re.search(r'NODE_IMAGE="docker.io/library/node:([^"]+)"', (ROOT / 'build-images.sh').read_text())[1]
        dev_node = re.search(r'FROM node:([^\s]+)', recipe)[1].removesuffix('-bookworm')
        self.assertEqual(prod_node, dev_node)
        entrypoint = (ROOT / 'ui/container-entrypoint.sh').read_text()
        self.assertIn('--immutable', entrypoint)
        self.assertIn('serve', entrypoint)

    def test_browser_ci_requires_image_extracted_host_css(self):
        workflow = (ROOT / '.github/workflows/validate.yml').read_text()
        self.assertRegex(workflow, r'ghcr.io/nethserver/core:latest@sha256:[a-f0-9]{64}')
        self.assertIn('test:e2e:dev', workflow)
        self.assertIn('test:e2e', workflow)
        self.assertIn('extract-core-css', workflow)
        self.assertIn('test-ui-dev', workflow)

    def test_production_builders_are_isolated_per_invocation(self):
        build = (ROOT / 'build-images.sh').read_text()
        self.assertIn('$$', build)
        self.assertIn('trap ', build)
        self.assertNotIn('buildah containers --format', build)

if __name__ == '__main__':
    unittest.main()
