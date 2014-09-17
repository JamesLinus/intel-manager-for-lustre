//
// INTEL CONFIDENTIAL
//
// Copyright 2013-2014 Intel Corporation All Rights Reserved.
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


(function () {
  'use strict';

  angular.module('server')
    .controller('ServerStatusStepCtrl', ['$scope', '$stepInstance', 'OVERRIDE_BUTTON_TYPES', 'data',
      function ServerStatusStepCtrl ($scope, $stepInstance, OVERRIDE_BUTTON_TYPES, data) {
        $scope.serverStatus = {
          /**
           * Used by filters to determine the context.
           * @param {Object} item
           * @returns {String}
           */
          getHostPath: function getHostPath (item) {
            return item.address;
          },
          /**
           * Update hostnames.
           * @param {String} pdsh
           * @param {Array} hostnames
           */
          pdshUpdate: function pdshUpdate (pdsh, hostnames) {
            if (hostnames)
              $scope.serverStatus.hostnames = hostnames;
          },
          /**
           * tells manager to perform a transition.
           * @param {String} action
           */
          transition: function transition (action) {
            off();

            if (action !== OVERRIDE_BUTTON_TYPES.OVERRIDE)
              $stepInstance.transition(action, { data: data });
          }
        };

        var off = data.statusSpark.onValue('pipeline', function assignToScope (response) {
          $scope.serverStatus.isValid = response.body.isValid;
          $scope.serverStatus.status = response.body.objects;
        });
      }])
      .factory('serverStatusStep', ['OVERRIDE_BUTTON_TYPES', function serverStatusStepFactory (OVERRIDE_BUTTON_TYPES) {
        return {
          templateUrl: 'iml/server/assets/html/server-status-step.html',
          controller: 'ServerStatusStepCtrl',
          transition: ['$transition', '$q', 'data', 'createHosts', 'hostProfile', 'openCommandModal',
            function transition ($transition, $q, data, createHosts, hostProfile, openCommandModal) {
              var step;

              if ($transition.action === 'previous') {
                step = $transition.steps.addServersStep;
              } else {
                step = $transition.steps.selectServerProfileStep;

                var hosts = createHosts(data.serverData);

                if ($transition.action === OVERRIDE_BUTTON_TYPES.PROCEED) {
                  hosts.then(function startCommand (response) {
                    if (_.compact(response.body.errors).length)
                      throw new Error(JSON.stringify(response.body.errors));

                    openCommandModal({
                      body: {
                        objects: _.pluck(response.body.objects, 'command')
                      }
                    });
                  });
                }

                data.hostProfileSpark = hosts.then(function getHostProfileSpark (response) {
                  var hosts = _.pluck(response.body.objects, 'host');

                  var deferred = $q.defer();
                  var hostSpark = hostProfile(data.flint, hosts);

                  hostSpark.onValue('data', function checkOnce () {
                    this.off();

                    deferred.resolve(hostSpark);
                  });

                  return deferred.promise;
                });
              }

              return {
                step: step,
                resolve: { data: data }
              };
            }
          ]
        };
      }]);
}());
