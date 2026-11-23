// Downloads the gallery photos from S3 into src/photo-cache/ and writes
// src/photo-cache/manifest.json (newest first, by EXIF capture date).
//
// Only changed files are downloaded: each file's S3 ETag is kept in the manifest,
// so a warm cache (locally, or restored by GitHub Actions) makes this fast.
// Uses the default AWS credential chain (AWS_PROFILE, `aws login`, OIDC in CI).

import { S3Client, ListObjectsV2Command, GetObjectCommand } from "@aws-sdk/client-s3";
import exifr from "exifr";
import { createWriteStream } from "node:fs";
import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { pipeline } from "node:stream/promises";
import path from "node:path";

const BUCKET = "jmtr-portfolio-photos";
const PREFIX = "photos/";
const REGION = "us-west-2";
const CACHE_DIR = path.resolve("src/photo-cache");
const MANIFEST = path.join(CACHE_DIR, "manifest.json");
const IMAGE_EXT = /\.(jpe?g|png|webp)$/i;

const s3 = new S3Client({ region: REGION });

async function listPhotos() {
  const photos = [];
  let token;
  do {
    const page = await s3.send(
      new ListObjectsV2Command({ Bucket: BUCKET, Prefix: PREFIX, ContinuationToken: token }),
    );
    for (const obj of page.Contents ?? []) {
      if (IMAGE_EXT.test(obj.Key)) photos.push({ key: obj.Key, etag: obj.ETag });
    }
    token = page.IsTruncated ? page.NextContinuationToken : undefined;
  } while (token);
  return photos;
}

// "photos/My Photo (1).JPG" -> "my-photo-1-.jpg": safe for file names and URLs.
const localName = (key) => {
  const base = path.basename(key);
  const ext = path.extname(base).toLowerCase().replace(".jpeg", ".jpg");
  const stem = path.basename(base, path.extname(base));
  return stem.replace(/[^A-Za-z0-9_-]+/g, "-") + ext;
};

// "DSCF0015" -> "DSCF0015"; "IMG_2336" -> "IMG 2336"
const altFromKey = (key) =>
  path.basename(key, path.extname(key)).replace(/[_-]+/g, " ").trim() || "Portfolio photo";

async function readManifest() {
  try {
    return JSON.parse(await readFile(MANIFEST, "utf8"));
  } catch {
    return [];
  }
}

async function download(key, file) {
  const res = await s3.send(new GetObjectCommand({ Bucket: BUCKET, Key: key }));
  await pipeline(res.Body, createWriteStream(file));
}

async function main() {
  await mkdir(CACHE_DIR, { recursive: true });
  const previous = new Map((await readManifest()).map((p) => [p.key, p]));
  const photos = await listPhotos();
  const existing = new Set(await readdir(CACHE_DIR));

  const names = new Set();
  const manifest = [];
  let downloaded = 0;
  for (const { key, etag } of photos) {
    const file = localName(key);
    if (names.has(file)) throw new Error(`Two photos map to the same file name: ${file}`);
    names.add(file);

    const cached = previous.get(key);
    let taken = cached?.taken ?? null;
    if (!cached || cached.etag !== etag || !existing.has(file)) {
      await download(key, path.join(CACHE_DIR, file));
      downloaded++;
      const exif = await exifr.parse(path.join(CACHE_DIR, file), ["DateTimeOriginal", "CreateDate"]).catch(() => null);
      const date = exif?.DateTimeOriginal ?? exif?.CreateDate;
      taken = date instanceof Date ? date.toISOString() : null;
    }
    manifest.push({ key, etag, file, alt: altFromKey(key), taken });
  }

  // Remove photos that were deleted from the bucket.
  for (const file of existing) {
    if (file !== "manifest.json" && !names.has(file)) await rm(path.join(CACHE_DIR, file));
  }

  // Newest first; photos without a capture date go last.
  manifest.sort((a, b) => (b.taken ?? "").localeCompare(a.taken ?? ""));
  await writeFile(MANIFEST, JSON.stringify(manifest, null, 2) + "\n");
  console.log(`photos: ${manifest.length} in gallery, ${downloaded} downloaded`);
}

await main();
