//
// INTEL CONFIDENTIAL
//
// Copyright 2013 Intel Corporation All Rights Reserved.
//
// The source code contained or described herein and all documents related
// to the source code ("Material") are owned by Intel Corporation or its
// suppliers or licensors. Title to the Material remains with Intel Corporation
// or its suppliers and licensors. The Material contains trade secrets and
// proprietary and confidential information of Intel or its suppliers and
// licensors. The Material is protected by worldwide copyright and trade secret
// laws and treaty provisions. No part of the Material may be used, copied,
// reproduced, modified, published, uploaded, posted, transmitted, distributed,
// or disclosed in any way without Intel's prior express written permission.
//
// No license under any patent, copyright, trade secret or other intellectual
// property right is granted to or conferred upon you by disclosure or delivery
// of the Materials, either expressly, by implication, inducement, estoppel or
// otherwise. Any license under such intellectual property rights must be
// express and approved by Intel in writing.


angular.module('hsm')
  .factory('hsmCdtTransformer', ['moment',
  function hsmCdtTransformerFactory(moment) {
    'use strict';

    /**
     * Transforms incoming stream data to compute HSM stats
     * @param {Array|undefined} newVal The new data.
     * @param {Object} deferred The deferred to pipe through.
     */
    return function transformer(resp, deferred) {
      var newVal = resp.body;

      if (!Array.isArray(newVal) )
        throw new Error('Transformer expects resp.body to be an array!');

      if (newVal.length === 0) {
        deferred.resolve(resp);
        return;
      }

      var dataPoints = [
        {
          key: 'waiting requests',
          values: []
        },
        {
          key: 'running actions',
          values: []
        },
        {
          key: 'idle workers',
          values: []
        }
      ];

      resp.body = newVal.reduce(function (arr, curr) {
        var waiting = curr.data.hsm_actions_waiting;
        var running = curr.data.hsm_actions_running;
        var idle = curr.data.hsm_agents_idle;
        var now = moment(curr.ts).utc().toDate();

        arr[0].values.push({
          y: waiting,
          x: now
        });
        arr[1].values.push({
          y: running,
          x: now
        });
        arr[2].values.push({
          y: idle,
          x: now
        });

        return arr;

      }, dataPoints);

      deferred.resolve(resp);
    };
  }
]);
