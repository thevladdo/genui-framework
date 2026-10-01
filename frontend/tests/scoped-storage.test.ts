/**
 * The profile on the visitor's device belongs to one backend and one key.
 * Another backend on the same origin reads nothing, and a record written before records carried a scope counts as absent.
 */

import 'fake-indexeddb/auto';
import { expect, test } from 'vitest';
import {
  createEmptyProfile,
  getProfile,
  profileScope,
  saveProfile,
} from 'genui-framework';

const seedLegacyRecord = () =>
  new Promise<void>((resolve, reject) => {
    const open = indexedDB.open('genui-profile-db', 1);
    open.onupgradeneeded = () => {
      open.result.createObjectStore('profiles');
      open.result.createObjectStore('conversation-history');
    };
    open.onsuccess = () => {
      const tx = open.result.transaction('profiles', 'readwrite');
      tx.objectStore('profiles').put(createEmptyProfile('legacy-user'), 'legacy-user');
      tx.oncomplete = () => {
        open.result.close();
        resolve();
      };
      tx.onerror = () => reject(tx.error);
    };
    open.onerror = () => reject(open.error);
  });

test('(f) a record written for one backend is not read by another, and unscoped records count as absent', async () => {
  await seedLegacyRecord();
  const a = profileScope('http://a.test/', 'pk_a');
  const b = profileScope('http://b.test', 'pk_a');
  const otherKey = profileScope('http://a.test', 'pk_other');

  expect(await getProfile('legacy-user', a)).toBeNull();
  expect(await getProfile('legacy-user')).toBeNull();

  const profile = createEmptyProfile('u1');
  profile.interests.topic = { value: 'solar', confidence: 0.9, updatedAt: '' } as any;
  await saveProfile(profile, a);

  expect((await getProfile('u1', a))?.interests.topic).toBeTruthy();
  expect(await getProfile('u1', profileScope('http://a.test', 'pk_a'))).not.toBeNull();
  expect(await getProfile('u1', b)).toBeNull();
  expect(await getProfile('u1', otherKey)).toBeNull();
  expect(await getProfile('u1')).toBeNull();
});
