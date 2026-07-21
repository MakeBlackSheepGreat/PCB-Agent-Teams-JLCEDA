import fs from 'fs-extra';
import ignore from 'ignore';
import JSZip from 'jszip';

import * as extensionConfig from '../extension.json';

function multiLineStrToArray(str: string): Array<string> {
	return str.split(/[\r\n]+/);
}

function main() {
	const filepathListWithoutFilter = fs.readdirSync(__dirname + '/../', { encoding: 'utf-8', recursive: true });
	const edaignoreListWithoutResolve = multiLineStrToArray(fs.readFileSync(__dirname + '/../.edaignore', { encoding: 'utf-8' }));
	const edaignoreList: Array<string> = [];
	for (const edaignoreLine of edaignoreListWithoutResolve) {
		if (edaignoreLine.endsWith('/') || edaignoreLine.endsWith('\\')) {
			edaignoreList.push(edaignoreLine.slice(0, edaignoreLine.length - 1));
		} else {
			edaignoreList.push(edaignoreLine);
		}
	}
	const edaignore = ignore().add(edaignoreList);
	const filepathListWithoutResolve = edaignore.filter(filepathListWithoutFilter);
	const fileList: Array<string> = [];
	for (const filepath of filepathListWithoutResolve) {
		if (fs.lstatSync(filepath).isFile()) {
			fileList.push(filepath.replace(/\\/g, '/'));
		}
	}

	fs.ensureDirSync(__dirname + '/dist/');

	const zip = new JSZip();
	for (const file of fileList) {
		zip.file(file, fs.createReadStream(__dirname + '/../' + file));
	}

	zip.generateNodeStream({ type: 'nodebuffer', streamFiles: true }).pipe(
		fs.createWriteStream(__dirname + '/dist/' + extensionConfig.name + '_v' + extensionConfig.version + '.eext'),
	);
}

main();
