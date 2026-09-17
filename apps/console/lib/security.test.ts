import { describe,it,expect } from 'vitest';
import { validCsrf,isLocalDevelopment } from './security';

describe('browser state-change boundary',()=>{
  const csrf='a'.repeat(64);
  it('requires matching token and exact origin',()=>{
    expect(validCsrf('http://localhost:3000','http://localhost:3000',csrf,csrf)).toBe(true);
    for(const origin of [null,'https://evil.example','http://localhost:3001'])
      expect(validCsrf(origin,'http://localhost:3000',csrf,csrf)).toBe(false);
    expect(validCsrf('http://localhost:3000','http://localhost:3000',csrf,'b'.repeat(64))).toBe(false);
    expect(validCsrf('http://localhost:3000','http://localhost:3000',undefined,csrf)).toBe(false);
  });
  it('never enables local identities for staging/production',()=>{
    for(const env of ['staging','production',undefined])expect(isLocalDevelopment(env,'development','http://localhost:3000')).toBe(false);
    expect(isLocalDevelopment('development','development','https://company.example')).toBe(false);
    expect(isLocalDevelopment('development','development','http://localhost:3000')).toBe(true);
  });
});
