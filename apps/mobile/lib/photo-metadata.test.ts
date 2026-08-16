import {describe,expect,it} from 'vitest';
import {extractGpsFromImageBytes,gpsExifSegment,injectGpsIntoJpeg} from './photo-metadata';

describe('photo metadata',()=>{
  it('round-trips New Zealand GPS through EXIF',()=>{
    const segment=gpsExifSegment({latitude:-43.5321,longitude:172.6362});
    const buffer=segment.buffer.slice(segment.byteOffset,segment.byteOffset+segment.byteLength) as ArrayBuffer;
    const gps=extractGpsFromImageBytes(buffer);
    expect(gps?.latitude).toBeCloseTo(-43.5321,4);
    expect(gps?.longitude).toBeCloseTo(172.6362,4);
  });

  it('keeps GPS when a HEIC-origin photo is represented as JPEG',async()=>{
    const jpeg=new Blob([new Uint8Array([0xff,0xd8,0xff,0xdb,0,1,2,3,0xff,0xd9])],{type:'image/jpeg'});
    const result=await injectGpsIntoJpeg(jpeg,{latitude:-43.5321,longitude:172.6362});
    const gps=extractGpsFromImageBytes(await result.arrayBuffer());
    expect(gps?.latitude).toBeCloseTo(-43.5321,4);
    expect(gps?.longitude).toBeCloseTo(172.6362,4);
  });
});
